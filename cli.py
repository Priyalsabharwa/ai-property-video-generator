#!/usr/bin/env python3
"""Command-line interface for the AI Property Video Generator.

Examples
  python cli.py --input sample_data/property.json --output output/sample_video.mp4
  python cli.py --input sample_data/property.json --orientation portrait --no-narration
  python cli.py --name "Sunrise Villa" --location "Baner, Pune" --price "Rs 1.4 Cr" \
      --type "3-BHK Villa" --features "3 Bedrooms, Private Garden" --images-dir my_photos/
"""
import argparse
import sys
from pathlib import Path

from generator import VideoOptions, ValidationError, generate_video
from generator.render import RenderError
from generator.validate import images_from_folder, load_json


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Turn property details + photos into a promo MP4.")
    src = p.add_argument_group("input (use --input JSON and/or the flags below; flags override JSON)")
    src.add_argument("--input", "-i", help="Property JSON file (see sample_data/property.json)")
    src.add_argument("--name")
    src.add_argument("--location")
    src.add_argument("--price")
    src.add_argument("--type", dest="property_type", help="e.g. '2-BHK Apartment'")
    src.add_argument("--features", help="Comma-separated key features")
    src.add_argument("--contact", help="Contact line, e.g. 'Call +91 90000 00000'")
    src.add_argument("--cta", help="Call-to-action text")
    src.add_argument("--images", nargs="+", help="Image file paths")
    src.add_argument("--images-dir", help="Folder of images (alternative to --images)")

    out = p.add_argument_group("output")
    out.add_argument("--output", "-o", default="output/property_video.mp4")
    out.add_argument("--orientation", choices=["landscape", "portrait"], default="landscape",
                     help="landscape 16:9 or portrait 9:16 (Reels/Shorts/WhatsApp status)")
    out.add_argument("--hd", action="store_true", help="1080p instead of 720p (slower)")
    out.add_argument("--fps", type=int, default=24)
    out.add_argument("--no-music", action="store_true")
    out.add_argument("--no-narration", action="store_true")
    out.add_argument("--llm", action="store_true",
                     help="Use Claude for narration (needs ANTHROPIC_API_KEY); fact-checked, falls back to template")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    try:
        data, images = ({}, [])
        if a.input:
            data, images = load_json(a.input)
        for k in ("name", "location", "price", "property_type", "features", "contact", "cta"):
            v = getattr(a, k)
            if v is not None:
                data[k] = v
        if a.images:
            images = a.images
        elif a.images_dir:
            images = images_from_folder(a.images_dir)
        if not data and not images:
            print("Error: nothing to do. Provide --input JSON or property flags (see --help).", file=sys.stderr)
            return 2

        opts = VideoOptions(orientation=a.orientation, hd=a.hd, fps=a.fps, music=not a.no_music,
                            narration=not a.no_narration, use_llm=a.llm)

        last = [-1]

        def progress(f, msg):
            pct = int(f * 100)
            if pct == last[0]:
                return
            last[0] = pct
            bar = "#" * int(f * 30)
            print(f"\r[{bar:<30}] {pct:3d}%  {msg:<24}", end="", flush=True)

        res = generate_video(data, images, a.output, opts, progress)
        print()
    except ValidationError as e:
        print("\nCannot create video - please fix the following:", file=sys.stderr)
        for m in e.problems:
            print(f"  - {m}", file=sys.stderr)
        return 2
    except RenderError as e:
        print(f"\nRendering failed: {e}", file=sys.stderr)
        return 3

    print(f"\nVideo saved : {res.output}  ({res.duration:.1f}s, {res.output.stat().st_size / 1e6:.1f} MB)")
    print(f"Preview     : {res.preview_image}")
    print(f"Script mode : {res.script_mode} | Narration: {res.narration_backend or 'none'}")
    if res.warnings:
        print("Warnings:")
        for w in res.warnings:
            print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
