import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator import VideoOptions, ValidationError, generate_video  # noqa: E402
from generator import script as S  # noqa: E402
from generator.validate import load_json, validate  # noqa: E402

SAMPLE = ROOT / "sample_data" / "property.json"


@pytest.fixture(scope="module")
def sample():
    data, imgs = load_json(SAMPLE)
    return data, imgs


def test_validate_ok(sample):
    p = validate(*sample)
    assert p.name == "Skyline Heights" and len(p.images) == 6 and len(p.features) == 5


def test_missing_required_fields_reported_together():
    with pytest.raises(ValidationError) as e:
        validate({"name": "X"}, [])
    msgs = " ".join(e.value.problems)
    assert "location" in msgs and "price" in msgs and "property_type" in msgs and "No usable images" in msgs


def test_bad_images_skipped_with_warning(sample, tmp_path):
    data, imgs = sample
    bad = tmp_path / "bad.jpg"
    bad.write_text("nope")
    p = validate(data, imgs[:3] + [str(bad), str(tmp_path / "missing.png")])
    assert len(p.images) == 3
    assert any("corrupt" in w for w in p.warnings) and any("not found" in w for w in p.warnings)


def test_more_than_8_images_truncated(sample):
    data, imgs = sample
    p = validate(data, imgs * 3)
    assert len(p.images) == 8


def test_scene_plan_and_image_matching(sample):
    p = validate(*sample)
    scenes = S.plan_scenes(p)
    assert [s.kind for s in scenes] == ["title"] + ["feature"] * 5 + ["price", "cta"]
    by_caption = {s.caption: p.images[s.image_index].name for s in scenes}
    assert "kitchen" in by_caption["Modular Kitchen"]
    assert "balcony" in by_caption["Spacious Balcony with City View"]
    assert "parking" in by_caption["Covered Parking"]


def test_template_narration_only_uses_input_facts(sample):
    p = validate(*sample)
    for s in S.plan_scenes(p):
        assert S.fact_check(s.narration, p) == [], s.narration


def test_fact_check_catches_hallucinations(sample):
    p = validate(*sample)
    assert any("swimming" in i or "pool" in i for i in S.fact_check("Enjoy the swimming pool.", p))
    assert any("999" in i for i in S.fact_check("Only 999 units left.", p))
    assert S.fact_check("A lovely 2-BHK Apartment for ₹85 Lakh.", p) == []


def test_llm_hallucination_falls_back_to_template(sample, monkeypatch):
    p = validate(*sample)
    monkeypatch.setattr(S, "llm_available", lambda: True)
    monkeypatch.setattr(S, "_llm_narrations", lambda p_, sc, m: ["Enjoy our rooftop pool and gym!"] * len(sc))
    scenes, warns, mode = S.build_script(p, use_llm=True)
    assert mode == "template" and any("fact-check" in w for w in warns)


def test_llm_clean_output_is_used(sample, monkeypatch):
    p = validate(*sample)
    monkeypatch.setattr(S, "llm_available", lambda: True)
    monkeypatch.setattr(S, "_llm_narrations", lambda p_, sc, m: [f"Presenting {s.caption}." for s in sc])
    scenes, warns, mode = S.build_script(p, use_llm=True)
    assert mode == "llm" and not warns


def test_llm_exception_falls_back(sample, monkeypatch):
    p = validate(*sample)
    monkeypatch.setattr(S, "llm_available", lambda: True)

    def boom(*a):
        raise RuntimeError("network down")
    monkeypatch.setattr(S, "_llm_narrations", boom)
    _, warns, mode = S.build_script(p, use_llm=True)
    assert mode == "template" and any("failed" in w for w in warns)


def test_end_to_end_small_render(sample, tmp_path):
    out = tmp_path / "v.mp4"
    res = generate_video(*sample, out, VideoOptions(fps=6, narration=False, music=True))
    assert out.exists() and out.stat().st_size > 10_000
    assert res.duration > 20 and res.preview_image.exists()


def test_cli_exit_codes(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "cli.py"), "--name", "X"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2 and "Cannot create video" in r.stderr and "Traceback" not in r.stderr
