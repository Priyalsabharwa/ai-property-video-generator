"""Streamlit UI:  streamlit run app.py"""
import tempfile
from pathlib import Path

import streamlit as st

from generator import ValidationError, VideoOptions, generate_video
from generator.render import RenderError
from generator.script import llm_available

SAMPLE_DIR = Path(__file__).parent / "sample_data"

st.set_page_config(page_title="AI Property Video Generator", page_icon="🏠", layout="wide")
st.title("🏠 AI Property Video Generator")
st.caption("Enter property details + 4-8 photos → get a ready-to-share promo video. No video editing needed.")

left, right = st.columns([1, 1])

with left:
    use_sample = st.checkbox("Use sample property (synthetic data)", value=False)
    d = dict(name="Skyline Heights", location="Green Valley Road, Pune", price="₹85 Lakh",
             property_type="2-BHK Apartment",
             features="2 Bedrooms, 2 Bathrooms\nModular Kitchen\nSpacious Balcony with City View\n24x7 Security\nCovered Parking",
             contact="Call +91 90000 00000", cta="Book your site visit today") if use_sample else {}
    name = st.text_input("Property name *", d.get("name", ""))
    location = st.text_input("Location *", d.get("location", ""))
    c1, c2 = st.columns(2)
    price = c1.text_input("Price *", d.get("price", ""), placeholder="₹85 Lakh")
    ptype = c2.text_input("Property type *", d.get("property_type", ""), placeholder="2-BHK Apartment")
    features = st.text_area("Key features (one per line, max 5)", d.get("features", ""), height=130)
    c3, c4 = st.columns(2)
    contact = c3.text_input("Contact", d.get("contact", ""))
    cta = c4.text_input("Call to action", d.get("cta", ""))
    uploads = [] if use_sample else st.file_uploader(
        "Property photos (4-8; file names like 'kitchen.jpg' help match photos to features)",
        type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

with right:
    st.subheader("Options")
    orientation = st.radio("Format", ["landscape", "portrait"], horizontal=True,
                           format_func=lambda x: "16:9 landscape" if x == "landscape" else "9:16 portrait (Reels/Shorts)")
    o1, o2, o3 = st.columns(3)
    narration = o1.checkbox("Narration", True)
    music = o2.checkbox("Music", True)
    hd = o3.checkbox("HD 1080p", False)
    use_llm = st.checkbox("Use Claude for narration (fact-checked)", False, disabled=not llm_available(),
                          help="Needs ANTHROPIC_API_KEY env var + `pip install anthropic`. Falls back to template.")
    go = st.button("🎬 Generate video", type="primary", use_container_width=True)
    slot = st.container()

if go:
    data = dict(name=name, location=location, price=price, property_type=ptype,
                features=features, contact=contact, cta=cta)
    with tempfile.TemporaryDirectory() as tmp:
        if use_sample:
            paths = [str(p) for p in sorted((SAMPLE_DIR / "images").glob("*.jpg"))]
        else:
            paths = []
            for i, f in enumerate(uploads or []):
                p = Path(tmp) / f"{i:02d}_{Path(f.name).name}"
                p.write_bytes(f.getbuffer())
                paths.append(str(p))
        out = Path(tmp) / "property_video.mp4"
        bar = slot.progress(0.0, "Starting")
        try:
            res = generate_video(data, paths, out,
                                 VideoOptions(orientation=orientation, hd=hd, music=music,
                                              narration=narration, use_llm=use_llm),
                                 lambda f, m: bar.progress(min(1.0, f), m))
            bar.empty()
            video_bytes = res.output.read_bytes()
            slot.success(f"Done! {res.duration:.0f}s video | script: {res.script_mode} | narration: {res.narration_backend or 'none'}")
            slot.video(video_bytes)
            slot.download_button("⬇️ Download MP4", video_bytes, "property_video.mp4", "video/mp4", use_container_width=True)
            for w in res.warnings:
                slot.warning(w)
            with slot.expander("Script used"):
                for i, s in enumerate(res.scenes, 1):
                    st.markdown(f"**{i}. {s.kind}** - _{s.caption}_  \n🎙 {s.narration}")
        except ValidationError as e:
            bar.empty()
            slot.error("Please fix the following and try again:\n\n" + "\n".join(f"- {m}" for m in e.problems))
        except RenderError as e:
            bar.empty()
            slot.error(f"Rendering failed: {e}")
