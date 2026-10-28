"""Audio: optional TTS narration + procedurally generated background music.

* Narration backends tried in order: espeak-ng/espeak (offline CLI), pyttsx3
  (offline), gTTS (online). If none work, the video is simply made without
  narration (a warning is returned, never a crash).
* Background music is synthesised with numpy (soft pad chords), so it is
  100% royalty-free and needs no downloaded assets.
"""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _to_wav(src: Path, dst: Path) -> bool:
    """Normalise any audio file to 44.1 kHz mono 16-bit wav using ffmpeg."""
    ff = find_ffmpeg()
    if not ff:
        return False
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR),
                        "-ac", "1", "-sample_fmt", "s16", str(dst)], capture_output=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 1000


def _tts_espeak(text: str, out: Path) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    raw = out.with_suffix(".raw.wav")
    for voice in ("en-in", "en"):
        r = subprocess.run([exe, "-v", voice, "-s", "150", "-p", "45", "-w", str(raw), text],
                           capture_output=True)
        if r.returncode == 0 and raw.exists():
            return _to_wav(raw, out)
    return False


def _tts_pyttsx3(text: str, out: Path) -> bool:
    try:
        import pyttsx3
        raw = out.with_suffix(".raw.wav")
        eng = pyttsx3.init()
        eng.save_to_file(text, str(raw))
        eng.runAndWait()
        return raw.exists() and _to_wav(raw, out)
    except Exception:
        return False


def _tts_gtts(text: str, out: Path) -> bool:
    try:
        from gtts import gTTS
        mp3 = out.with_suffix(".mp3")
        gTTS(text=text, lang="en", tld="co.in").save(str(mp3))
        return _to_wav(mp3, out)
    except Exception:
        return False


BACKENDS = {"espeak": _tts_espeak, "pyttsx3": _tts_pyttsx3, "gtts": _tts_gtts}


def pick_backend(workdir: Path) -> str | None:
    """Find the first TTS backend that actually works on this machine."""
    test = workdir / "_probe.wav"
    for name, fn in BACKENDS.items():
        try:
            if fn("Hello.", test):
                return name
        except Exception:
            continue
    return None


def synthesize(text: str, out: Path, backend: str) -> bool:
    try:
        return BACKENDS[backend](text, out)
    except Exception:
        return False


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def make_music(seconds: float) -> np.ndarray:
    """Calm ambient pad: Cmaj7 - Am7 - Fmaj7 - G6, 4 s per chord, soft attack/release."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    chords = [[261.63, 329.63, 392.00, 493.88], [220.00, 261.63, 329.63, 392.00],
              [174.61, 261.63, 329.63, 440.00], [196.00, 246.94, 293.66, 329.63]]
    out = np.zeros(n, dtype=np.float32)
    seg = 4.0
    for k in range(int(np.ceil(seconds / seg))):
        a, b = int(k * seg * SR), min(n, int((k + 1) * seg * SR + 0.5 * SR))  # slight overlap
        tt = t[a:b] - t[a]
        env = np.minimum(1, tt / 1.2) * np.minimum(1, (tt[-1] - tt) / 1.2 + 0.0)
        for f in chords[k % 4]:
            tone = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)
                    + 0.1 * np.sin(2 * np.pi * 3 * f * tt))
            tone *= 1 + 0.08 * np.sin(2 * np.pi * 0.25 * tt)  # gentle shimmer
            out[a:b] += (env * tone).astype(np.float32) / 4
        # soft bass note
        out[a:b] += (env * np.sin(2 * np.pi * chords[k % 4][0] / 2 * tt) * 0.35).astype(np.float32)
    out /= max(1e-6, np.abs(out).max())
    fade = int(1.5 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def mix_track(total_seconds: float, narration: list[tuple[float, Path]], music: bool, out: Path) -> bool:
    """Mix music (ducked under speech) + narration clips placed at given start times."""
    n = int((total_seconds + 0.5) * SR)
    track = np.zeros(n, dtype=np.float32)
    voice = np.zeros(n, dtype=np.float32)
    for start, wav in narration:
        clip = read_wav(wav)
        a = int(start * SR)
        b = min(n, a + len(clip))
        if b > a:
            voice[a:b] += clip[: b - a]
    if music:
        m = make_music(total_seconds + 0.5)[:n]
        has_voice = narration != []
        # duck music while narration is speaking
        gain = np.full(n, 0.22 if not has_voice else 0.16, dtype=np.float32)
        if has_voice:
            env = np.convolve(np.abs(voice), np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
            gain *= 1 - 0.6 * np.clip(env * 12, 0, 1)
        track += m * gain
    if narration:
        track += voice * 0.95
    if not np.any(track):
        return False
    write_wav(out, track)
    return True
