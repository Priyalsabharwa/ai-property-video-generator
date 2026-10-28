"""Script (captions + narration) generation and scene planning.

Two modes:
  * template (default): deterministic, offline, zero hallucination risk.
  * llm (optional): Claude writes narration lines only. Captions stay
    template-based. Output is fact-checked; on any failure we fall back to
    the template script.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .validate import PropertyInput

DEFAULT_CTA = "Contact us to book a site visit"


@dataclass
class Scene:
    kind: str                 # title | feature | price | cta
    caption: str              # large on-screen text
    subcaption: str           # smaller line under the caption
    narration: str            # voice-over text (may be empty)
    image_index: int = 0
    duration: float = 4.0


_STOP = {"the", "and", "with", "a", "of", "in", "for", "24x7", "img", "image", "photo", "jpg", "jpeg", "png"}


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def _tokens(text: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z]+", text.lower()) if t not in _STOP and len(t) > 2}


def assign_images(p: PropertyInput, scenes: list[Scene]) -> None:
    """Pick a photo per scene.

    1) Match feature text to image filenames by keyword (e.g. 'Modular Kitchen' ->
       04_kitchen.jpg). 2) Otherwise use the least-used image so photos repeat as
       little as possible. Title/CTA use the first image (assumed exterior).
    """
    n = len(p.images)
    names = [_tokens(img.stem) for img in p.images]
    use = [0] * n
    scenes[0].image_index = 0
    use[0] += 1
    for s in scenes[1:]:
        if s.kind == "cta":
            s.image_index = 0
            continue
        pick = None
        if s.kind == "feature":
            want = _tokens(s.caption)
            scored = [(len(want & names[i]), -use[i], -i, i) for i in range(n)]
            best = max(scored)
            if best[0] > 0:
                pick = best[3]
        if pick is None:
            pick = min(range(n), key=lambda i: (use[i], i if s.kind != "price" else -i))
        s.image_index = pick
        use[pick] += 1


def plan_scenes(p: PropertyInput) -> list[Scene]:
    """Template script: title -> one scene per feature -> price/location -> CTA."""
    scenes = [Scene("title", p.name, f"{p.property_type} in {p.location}",
                    f"Welcome to {p.name}, a {p.property_type} in {p.location}.", 0, 4.0)]
    for feat in p.features:
        scenes.append(Scene("feature", feat, p.name, f"{feat}.", 0, 4.0))
    scenes.append(Scene("price", p.price, f"{p.property_type} | {p.location}",
                        f"Priced at {p.price}.", 0, 4.0))
    cta = p.cta or DEFAULT_CTA
    scenes.append(Scene("cta", cta, p.contact or "Send us an enquiry today",
                        f"{cta}." + (f" {p.contact}." if p.contact else ""), 0, 5.0))
    assign_images(p, scenes)
    return scenes


# ---------------------------------------------------------------- fact checking
# Claim words an LLM tends to invent. If one appears in generated narration but
# nowhere in the supplied input, the output is rejected.
RISKY_TERMS = [
    "pool", "swimming", "gym", "garden", "clubhouse", "club house", "lift", "elevator",
    "view", "sea", "lake", "metro", "school", "hospital", "mall", "park", "terrace",
    "furnished", "luxury", "luxurious", "discount", "offer", "emi", "loan", "rera",
    "guaranteed", "returns", "investment", "ready to move", "possession", "sq ft", "sqft",
    "floor", "bhk", "bedroom", "bathroom", "parking", "security", "kitchen", "balcony",
]
_NUM = re.compile(r"\d[\d,\.]*")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9₹ ]+", " ", s.lower())


def fact_check(text: str, p: PropertyInput) -> list[str]:
    """Return a list of violations (empty list = passed)."""
    src = _norm(p.facts_text())
    src_nums = {re.sub(r"\D", "", m) for m in _NUM.findall(p.facts_text())}
    issues = []
    for m in _NUM.findall(text):
        digits = re.sub(r"\D", "", m)
        if digits and digits not in src_nums:
            issues.append(f"number '{m}' not in input")
    low = _norm(text)
    for term in RISKY_TERMS:
        if re.search(rf"\b{re.escape(term)}", low) and not re.search(rf"\b{re.escape(term)}", src):
            issues.append(f"unsupported claim word '{term}'")
    return issues


# ------------------------------------------------------------------ LLM option
def llm_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _llm_narrations(p: PropertyInput, scenes: list[Scene], model: str) -> list[str]:
    import anthropic
    client = anthropic.Anthropic()
    brief = [{"scene": i, "kind": s.kind, "caption": s.caption, "subcaption": s.subcaption}
             for i, s in enumerate(scenes)]
    prompt = (
        "Write a short, warm, professional voice-over line (max 18 words) for each scene of a "
        "real-estate promo video. STRICT RULES: use ONLY the facts in the scene data below; do not "
        "add amenities, numbers, nearby places, adjectives implying unlisted features, or promises. "
        "Respond with ONLY a JSON array of strings, one per scene, same order.\n\n"
        f"Scene data:\n{json.dumps(brief, ensure_ascii=False)}")
    resp = client.messages.create(model=model, max_tokens=800,
                                  messages=[{"role": "user", "content": prompt}])
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    lines = json.loads(raw)
    if not (isinstance(lines, list) and len(lines) == len(scenes) and all(isinstance(x, str) for x in lines)):
        raise ValueError("LLM returned wrong shape")
    return lines


def build_script(p: PropertyInput, use_llm: bool = False,
                 model: str = "claude-sonnet-4-5") -> tuple[list[Scene], list[str], str]:
    """Returns (scenes, warnings, mode_used)."""
    scenes, warnings = plan_scenes(p), []
    if not use_llm:
        return scenes, warnings, "template"
    if not llm_available():
        warnings.append("LLM mode requested but ANTHROPIC_API_KEY / 'anthropic' package missing: used template script.")
        return scenes, warnings, "template"
    try:
        lines = _llm_narrations(p, scenes, model)
        issues = [f"scene {i}: {iss}" for i, l in enumerate(lines) for iss in fact_check(l, p)]
        if issues:
            warnings.append("LLM narration failed fact-check (" + "; ".join(issues[:4]) + "): used template script.")
            return scenes, warnings, "template"
        for s, l in zip(scenes, lines):
            s.narration = l
        return scenes, warnings, "llm"
    except Exception as e:  # network, auth, bad JSON... never crash the pipeline
        warnings.append(f"LLM call failed ({type(e).__name__}): used template script.")
        return scenes, warnings, "template"
