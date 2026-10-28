"""Frame rendering (Pillow) and MP4 encoding (ffmpeg via a pipe).

Each scene = one photo with a slow Ken Burns zoom/pan + a readable text overlay.
Scenes are joined with crossfades. No MoviePy/ImageMagick dependency.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .audio import find_ffmpeg
from .script import Scene

ACCENT = (240, 140, 40)
WHITE = (255, 255, 255)
SOFT = (225, 230, 240)

_FONT_BOLD = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "Arial Bold.ttf", "arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_FONT_REG = ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "Arial.ttf", "arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


class RenderError(Exception):
    pass


def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    for name in (_FONT_BOLD if bold else _FONT_REG):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)  # Pillow >= 10.1


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text: str, size: int, bold: bool, max_w: int, max_lines: int):
    """Shrink font until the text fits in max_lines."""
    while True:
        f = _font(size, bold)
        lines = _wrap(draw, text, f, max_w)
        if (len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines)) or size <= 14:
            return f, lines
        size -= 2


def _draw_lines(draw, lines, font, x, y, fill, anchor_center_w=None, spacing=1.18):
    """Draw lines; returns the y after the block. Centered if anchor_center_w given."""
    for l in lines:
        w = draw.textlength(l, font=font)
        xx = (anchor_center_w - w) / 2 if anchor_center_w else x
        draw.text((xx, y), l, font=font, fill=fill, stroke_width=max(1, font.size // 22),
                  stroke_fill=(0, 0, 0, 170))
        y += int(font.size * spacing)
    return y


def _gradient(W: int, H: int, y0: int, y1: int, a0: int, a1: int) -> Image.Image:
    """RGBA black layer whose alpha ramps from a0 (at y0) to a1 (at y1), clamped outside."""
    col = Image.new("L", (1, H))
    for y in range(H):
        t = min(1.0, max(0.0, (y - y0) / max(1, y1 - y0)))
        col.putpixel((0, y), int(a0 + (a1 - a0) * t))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(col.resize((W, H)))
    return layer


@dataclass
class Prepared:
    base: Image.Image       # oversized, cover-cropped photo (for Ken Burns)
    shade: Image.Image      # static darkening layer (RGBA)
    text: Image.Image       # text layer (RGBA) - faded in per frame
    duration: float
    flip: bool              # pan direction


ZOOM = 0.13   # fraction of zoom-in over the scene


def _prepare(scene: Scene, photo: Path, idx: int, W: int, H: int) -> Prepared:
    s = min(W, H) / 720 if W >= H else W / 720
    big = (int(W * 1.15), int(H * 1.15))
    with Image.open(photo) as im:
        base = ImageOps.fit(ImageOps.exif_transpose(im).convert("RGB"), big, Image.LANCZOS)

    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(text)
    mw = int(W * 0.84)
    pad = int(W * 0.08)

    if scene.kind == "feature":
        shade = _gradient(W, H, int(H * 0.52), int(H * 0.88), 0, 205)
        f1, l1 = _fit(d, scene.caption, int(46 * s), True, mw - int(24 * s), 3)
        f2 = _font(int(26 * s), False)
        h1 = len(l1) * int(f1.size * 1.18)
        y = int(H * 0.93) - h1 - int(26 * s) - int(10 * s)
        d.rounded_rectangle((pad, y + 4, pad + int(8 * s), y + h1 + int(34 * s)), 4, fill=ACCENT)
        y = _draw_lines(d, l1, f1, pad + int(26 * s), y, WHITE)
        _draw_lines(d, [scene.subcaption], f2, pad + int(26 * s), y + int(6 * s), SOFT)
    else:
        a_over = {"title": 120, "price": 135, "cta": 175}[scene.kind]
        shade = Image.new("RGBA", (W, H), (0, 0, 0, a_over))
        big_size = {"title": 66, "price": 96, "cta": 54}[scene.kind]
        f1, l1 = _fit(d, scene.caption, int(big_size * s), True, mw, 3)
        f2, l2 = _fit(d, scene.subcaption, int(32 * s), False, mw, 2)
        label = {"title": None, "price": "PRICE", "cta": "ENQUIRE NOW"}[scene.kind]
        h = len(l1) * int(f1.size * 1.18) + int(30 * s) + len(l2) * int(f2.size * 1.18)
        y = (H - h) // 2 - (int(20 * s) if label else 0)
        if label:
            fl = _font(int(24 * s), True)
            lw = d.textlength(label, font=fl)
            d.text(((W - lw) / 2, y - int(40 * s)), label, font=fl, fill=ACCENT)
        y = _draw_lines(d, l1, f1, 0, y, WHITE, anchor_center_w=W)
        d.rounded_rectangle(((W - 90 * s) / 2, y + 8 * s, (W + 90 * s) / 2, y + 13 * s), 3, fill=ACCENT)
        _draw_lines(d, l2, f2, 0, y + int(30 * s), SOFT, anchor_center_w=W)

    return Prepared(base, shade, text, scene.duration, flip=bool(idx % 2))


def _scene_frame(p: Prepared, t: float, W: int, H: int) -> Image.Image:
    u = min(1.0, max(0.0, t / p.duration))
    e = u * u * (3 - 2 * u)                       # ease in-out
    bw, bh = p.base.size
    cw, ch = bw * (1 - ZOOM * e), bh * (1 - ZOOM * e)
    a, b = (0.65, 0.35) if p.flip else (0.35, 0.65)
    px = a + (b - a) * u
    x0, y0 = (bw - cw) * px, (bh - ch) * 0.5
    img = p.base.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)).convert("RGBA")
    img = Image.alpha_composite(img, p.shade)
    # text fades + slides in over the first 0.6 s (after a short 0.3 s delay)
    f = min(1.0, max(0.0, (t - 0.3) / 0.6))
    if f > 0:
        layer = p.text
        if f < 1:
            moved = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            moved.paste(layer, (0, int((1 - f) * 18)))
            moved.putalpha(moved.getchannel("A").point(lambda v: int(v * f)))
            layer = moved
        img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def _timeline(prepared: list[Prepared], overlap: float):
    starts, t = [], 0.0
    for p in prepared:
        starts.append(t)
        t += p.duration - overlap
    total = starts[-1] + prepared[-1].duration
    return starts, total


def total_duration(durations: list[float], overlap: float) -> float:
    return sum(durations) - overlap * (len(durations) - 1)


def frame_at(prepared, starts, T, W, H, overlap, total) -> Image.Image:
    active = [i for i, p in enumerate(prepared) if starts[i] <= T < starts[i] + p.duration]
    if not active:
        active = [len(prepared) - 1]
    i = active[-1]
    fr = _scene_frame(prepared[i], T - starts[i], W, H)
    if len(active) == 2:        # crossfade: previous scene fading out under the new one
        j = active[0]
        prev = _scene_frame(prepared[j], T - starts[j], W, H)
        fr = Image.blend(prev, fr, min(1.0, (T - starts[i]) / overlap))
    # global fade from/to black
    k = 1.0
    if T < 0.5:
        k = T / 0.5
    elif T > total - 0.8:
        k = max(0.0, (total - T) / 0.8)
    if k < 1.0:
        fr = Image.blend(Image.new("RGB", (W, H)), fr, k)
    return fr


def prepare_scenes(scenes: list[Scene], photos: list[Path], W: int, H: int) -> list[Prepared]:
    try:
        return [_prepare(s, photos[s.image_index % len(photos)], i, W, H) for i, s in enumerate(scenes)]
    except Exception as e:
        raise RenderError(f"Could not process an image ({type(e).__name__}: {e}).")


def contact_sheet(prepared, starts, W, H, overlap, total, out: Path) -> Path:
    """One thumbnail per scene (captured ~2 s in) tiled into a PNG preview."""
    thumbs = []
    for i, p in enumerate(prepared):
        T = min(total - 1.0, starts[i] + min(2.2, p.duration * 0.6))
        thumbs.append(frame_at(prepared, starts, T, W, H, overlap, total).resize((W // 3, H // 3)))
    cols = 3 if W >= H else 4
    rows = (len(thumbs) + cols - 1) // cols
    tw, th = thumbs[0].size
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * th + (rows + 1) * 8), (24, 26, 32))
    for k, t in enumerate(thumbs):
        sheet.paste(t, (8 + (k % cols) * (tw + 8), 8 + (k // cols) * (th + 8)))
    sheet.save(out)
    return out


def render_video(prepared: list[Prepared], W: int, H: int, fps: int, overlap: float,
                 audio_path: Path | None, out: Path,
                 progress: Callable[[float, str], None] | None = None) -> float:
    ff = find_ffmpeg()
    if not ff:
        raise RenderError("ffmpeg not found. Install ffmpeg (https://ffmpeg.org) or `pip install imageio-ffmpeg`.")
    starts, total = _timeline(prepared, overlap)
    n = int(round(total * fps))
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p"]
    if audio_path:
        cmd += ["-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}"]
    cmd += ["-movflags", "+faststart", str(out)]

    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        try:
            for k in range(n):
                fr = frame_at(prepared, starts, k / fps, W, H, overlap, total)
                proc.stdin.write(fr.tobytes())
                if progress and k % 12 == 0:
                    progress(k / n, "Rendering frames")
            proc.stdin.close()
        except BrokenPipeError:
            pass
        except BaseException:
            proc.kill()
            out.unlink(missing_ok=True)   # never leave a half-written MP4
            raise
        proc.wait()
        if proc.returncode != 0:
            err.seek(0)
            out.unlink(missing_ok=True)
            raise RenderError("ffmpeg failed: " + err.read().decode(errors="ignore")[-400:])
    if progress:
        progress(1.0, "Done")
    return total
