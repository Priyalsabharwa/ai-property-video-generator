"""End-to-end orchestration: validate -> script -> narration -> render -> mix -> MP4."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import audio
from .render import (RenderError, contact_sheet, prepare_scenes, render_video,
                     total_duration, _timeline)
from .script import Scene, build_script
from .validate import validate

OVERLAP = 0.6  # seconds of crossfade between scenes


@dataclass
class VideoOptions:
    orientation: str = "landscape"   # landscape (16:9) | portrait (9:16, for Reels/Shorts)
    hd: bool = False                 # False = 720p, True = 1080p
    fps: int = 24
    music: bool = True
    narration: bool = True
    use_llm: bool = False
    llm_model: str = "claude-sonnet-4-5"

    def size(self) -> tuple[int, int]:
        short, long_ = (1080, 1920) if self.hd else (720, 1280)
        return (long_, short) if self.orientation == "landscape" else (short, long_)


@dataclass
class GenerationResult:
    output: Path
    duration: float
    warnings: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    script_mode: str = "template"
    narration_backend: str | None = None
    preview_image: Path | None = None


def generate_video(data: dict, image_paths: list[str], output: str | Path,
                   options: VideoOptions | None = None,
                   progress: Callable[[float, str], None] | None = None) -> GenerationResult:
    """Main entry point. Raises ValidationError (bad input) or RenderError (encode problem)."""
    opt = options or VideoOptions()
    say = progress or (lambda f, m: None)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    say(0.02, "Validating input")
    prop = validate(data, image_paths)
    warnings = list(prop.warnings)

    say(0.05, "Writing script")
    scenes, w, mode = build_script(prop, opt.use_llm, opt.llm_model)
    warnings += w

    W, H = opt.size()
    backend = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        narr_files: list[tuple[int, Path]] = []
        if opt.narration:
            say(0.08, "Generating narration")
            backend = audio.pick_backend(tmp)
            if backend is None:
                warnings.append("No text-to-speech engine available (install espeak-ng, pyttsx3 or gTTS): video has no narration.")
            else:
                for i, s in enumerate(scenes):
                    if not s.narration:
                        continue
                    wav = tmp / f"n{i}.wav"
                    if audio.synthesize(s.narration, wav, backend):
                        narr_files.append((i, wav))
                        # make the scene long enough for its narration to finish
                        s.duration = max(s.duration, audio.wav_seconds(wav) + 1.0)
                    else:
                        warnings.append(f"Narration failed for scene {i + 1}; scene left silent.")

        say(0.12, "Preparing scenes")
        prepared = prepare_scenes(scenes, prop.images, W, H)
        starts, total = _timeline(prepared, OVERLAP)

        audio_path = None
        if opt.music or narr_files:
            say(0.15, "Mixing audio")
            clips = [(starts[i] + 0.5, wav) for i, wav in narr_files]
            ap = tmp / "mix.wav"
            if audio.mix_track(total, clips, opt.music, ap):
                audio_path = ap

        def sub(f, m):
            say(0.2 + 0.78 * f, m)

        dur = render_video(prepared, W, H, opt.fps, OVERLAP, audio_path, out, sub)
        preview = contact_sheet(prepared, starts, W, H, OVERLAP, total, out.with_suffix(".preview.png"))

    return GenerationResult(out, dur, warnings, scenes, mode, backend, preview)
