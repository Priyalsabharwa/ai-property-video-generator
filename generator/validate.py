"""Input loading and validation.

Philosophy: hard-fail only when a video cannot be made at all (missing core
facts, zero usable images). Everything else degrades gracefully with a warning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

REQUIRED_FIELDS = ["name", "location", "price", "property_type"]
MIN_IMAGES, MAX_IMAGES = 4, 8
MAX_FEATURES = 5
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class ValidationError(Exception):
    """Raised when the input cannot produce a video. Holds a list of messages."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class PropertyInput:
    name: str
    location: str
    price: str
    property_type: str
    features: list[str] = field(default_factory=list)
    contact: str = ""
    cta: str = ""
    images: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def facts_text(self) -> str:
        """All supplied text, used by the fact-checker."""
        parts = [self.name, self.location, self.price, self.property_type,
                 self.contact, self.cta, *self.features]
        return " ".join(parts)


def load_json(path: str | Path) -> tuple[dict, list[str]]:
    """Read a property JSON file. Returns (data, image paths resolved vs. the JSON)."""
    p = Path(path)
    if not p.exists():
        raise ValidationError([f"Input file not found: {p}"])
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValidationError([f"Input file is not valid JSON ({e.msg} at line {e.lineno})."])
    if not isinstance(data, dict):
        raise ValidationError(["Input JSON must be an object with property fields."])
    imgs = [str(p.parent / i) if not Path(i).is_absolute() else i
            for i in data.get("images", []) if isinstance(i, str)]
    return data, imgs


def images_from_folder(folder: str | Path) -> list[str]:
    f = Path(folder)
    if not f.is_dir():
        raise ValidationError([f"Image folder not found: {f}"])
    return [str(x) for x in sorted(f.iterdir()) if x.suffix.lower() in IMAGE_EXTS]


def _clean(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def validate(data: dict, image_paths: list[str]) -> PropertyInput:
    problems: list[str] = []
    warnings: list[str] = []

    for f in REQUIRED_FIELDS:
        if not _clean(data.get(f)):
            problems.append(f"Missing required field '{f}'.")

    features_raw = data.get("features") or []
    if isinstance(features_raw, str):  # allow "a, b, c" or newline separated
        features_raw = features_raw.replace("\n", ",").split(",")
    features = [_clean(x) for x in features_raw if _clean(x)]
    if not features:
        warnings.append("No key features supplied: video will have no feature scenes.")
    if len(features) > MAX_FEATURES:
        warnings.append(f"{len(features)} features supplied; only the first {MAX_FEATURES} are used.")
        features = features[:MAX_FEATURES]

    contact, cta = _clean(data.get("contact")), _clean(data.get("cta"))
    if not contact and not cta:
        warnings.append("No contact/CTA text supplied: closing scene will use a generic enquiry prompt.")

    good: list[Path] = []
    for raw in image_paths:
        p = Path(raw)
        if not p.exists():
            warnings.append(f"Image not found, skipped: {p.name}")
            continue
        try:
            with Image.open(p) as im:
                im.verify()
            good.append(p)
        except (UnidentifiedImageError, OSError):
            warnings.append(f"Image unreadable or corrupt, skipped: {p.name}")
    if not good:
        problems.append("No usable images. Provide 4-8 valid image files (jpg/png/webp).")
    else:
        if len(good) < MIN_IMAGES:
            warnings.append(f"Only {len(good)} usable image(s) (recommended {MIN_IMAGES}-{MAX_IMAGES}); images will be reused across scenes.")
        if len(good) > MAX_IMAGES:
            warnings.append(f"{len(good)} images supplied; only the first {MAX_IMAGES} are used.")
            good = good[:MAX_IMAGES]

    if problems:
        raise ValidationError(problems)

    return PropertyInput(
        name=_clean(data["name"]), location=_clean(data["location"]),
        price=_clean(data["price"]), property_type=_clean(data["property_type"]),
        features=features, contact=contact, cta=cta, images=good, warnings=warnings)
