# 🏠 AI Property Video Generator

Turns property details + 4-8 photos into a short (~35 s), ready-to-share promo **MP4** — title scene, feature scenes with text overlays, price scene, enquiry CTA, crossfades, optional narration and background music. **No manual video editing.**

Built for the Realty Assistant *AI Content Creation / Multimedia* assignment.

| | |
|---|---|
| Sample video (16:9) | `output/sample_video.mp4` |
| Sample video (9:16, Reels / WhatsApp status) | `output/sample_video_portrait.mp4` |
| Scene contact sheet | `output/sample_video.preview.png` |
| Sample input | `sample_data/property.json` + `sample_data/images/` (synthetic illustrations) |

---

## Quick start

```bash
# 1. Python 3.10+ ; ffmpeg is bundled via imageio-ffmpeg (system ffmpeg is used if present)
pip install -r requirements.txt

# 2. (optional, for offline voice-over)  Linux: sudo apt install espeak-ng   |  macOS: brew install espeak-ng

# 3a. Command line
python cli.py --input sample_data/property.json --output output/sample_video.mp4

# 3b. Web UI (form + preview + download button)
streamlit run app.py
```

Core install needs only `Pillow`, `numpy`, `imageio-ffmpeg`. Narration, Streamlit and the LLM option are all optional — the tool degrades gracefully without them.

### CLI examples

```bash
# Vertical video for Reels/Shorts, no voice
python cli.py -i sample_data/property.json --orientation portrait --no-narration -o output/reel.mp4

# No JSON at all - everything via flags
python cli.py --name "Sunrise Villa" --location "Baner, Pune" --price "₹1.4 Cr" \
  --type "3-BHK Villa" --features "3 Bedrooms, Private Garden, Modular Kitchen" \
  --contact "Call +91 90000 00000" --cta "Visit this weekend" --images-dir my_photos/

# Claude-written narration (fact-checked, falls back to template on any problem)
export ANTHROPIC_API_KEY=...   # never commit this
python cli.py -i sample_data/property.json --llm
```

Run `python cli.py --help` for all options (`--hd`, `--fps`, `--no-music`, ...).

### Input format (`sample_data/property.json`)

| Field | Required | Notes |
|---|---|---|
| `name`, `location`, `price`, `property_type` | ✅ | Shown verbatim (e.g. `"₹85 Lakh"`) |
| `features` | optional | List (or comma/newline string). First 5 used; one scene each |
| `contact`, `cta` | optional | Closing scene text. Generic prompt used if both missing |
| `images` | ✅ (≥1 valid) | Paths relative to the JSON. 4-8 recommended |

**Tip:** name photos after what they show (`kitchen.jpg`, `balcony.jpg`) — the tool matches each feature to the right photo by filename keywords (see below).

---

## How it works

```
property.json / form ─► validate ─► script (template | LLM + fact-check) ─► scene plan + photo matching
                                                                   │
        narration (TTS) ─► scene durations ──────────────────────► render frames (Pillow) ─► ffmpeg ─► MP4
        music (synthesised) ─► mix + duck under voice ─────────────────────────────────────────┘
```

| Module | Responsibility |
|---|---|
| `generator/validate.py` | Load/clean input; hard errors only when a video is impossible, otherwise warnings |
| `generator/script.py` | Scene plan, captions, narration (template or LLM), **fact-checker**, photo↔feature matching |
| `generator/audio.py` | TTS backends (espeak-ng → pyttsx3 → gTTS), procedural background music, mixing/ducking |
| `generator/render.py` | Ken Burns zoom/pan, text overlays, crossfades, fades, ffmpeg pipe encode (H.264 + AAC) |
| `generator/pipeline.py` | Orchestration; scene length stretches to fit narration |
| `cli.py` / `app.py` | Command line / Streamlit UI |

Video structure: **Title → one scene per feature (≤5) → Price & location → Enquiry CTA**.

### Key decisions

* **Template by default, AI optional.** Captions are always template-generated from the input, so on-screen facts can never be wrong. This is a deliberate, justified rule-based choice for the part where accuracy matters most.
* **Pillow + direct ffmpeg pipe instead of MoviePy/ImageMagick** — fewer dependencies, no ImageMagick policy/font headaches, deterministic output on any OS.
* **Music is synthesised in code** (soft pad chords), so it is royalty-free by construction and needs no downloaded assets.
* **Photo ↔ feature matching:** feature words are matched to image filename keywords (`"Modular Kitchen"` → `04_kitchen.jpg`); unmatched scenes get the least-used photo so repeats are minimised. Title/CTA use the first image (assumed exterior).
* **Safe failure:** bad input → readable error list + exit code 2 (CLI) or red message box (UI). A failed encode deletes any half-written MP4.

---

## 🤖 AI usage (what it does, what it sees, how it is checked)

| Question | Answer |
|---|---|
| **What does the AI do?** | *Optional* (`--llm`): writes the short voice-over line for each scene. Nothing else — captions, prices, scene order and images are not AI-controlled. |
| **What information does it use?** | Only the scene data derived from the user's input (caption/sub-caption per scene). No photos are sent; no customer PII. |
| **How is its output checked?** | `fact_check()` rejects the whole LLM script if it (a) contains any **number** not present in the input, or (b) uses a **claim word** (pool, gym, garden, lift, view, metro, school, luxury, parking, …) that does not appear in the input, or (c) is not a JSON list of exactly one string per scene. On any failure, network error or missing key → automatic **fallback to the template script** with a warning. |
| **Verified by** | `tests/test_core.py` mocks an LLM that invents *"rooftop pool and gym"* and asserts fallback; also asserts template narration passes its own checker. |

Models / libraries / external services:

| Item | Use | Network? |
|---|---|---|
| Anthropic Claude API (`claude-sonnet-4-5`, configurable) | optional narration text | yes, only with `--llm` |
| espeak-ng | default offline TTS voice | no |
| pyttsx3 / gTTS | alternative TTS (gTTS = Google, online) | gTTS only |
| Pillow, numpy | frame rendering, audio synthesis | no |
| ffmpeg (via imageio-ffmpeg) | H.264/AAC encoding | no |
| Streamlit | web UI | no |

No API keys, passwords or real customer data are included. Sample photos are **synthetic illustrations** generated by `sample_data/make_sample_images.py`.

---

## Error handling (demo-able)

| Situation | Behaviour |
|---|---|
| Missing name/location/price/type | Lists *all* missing fields, exit 2 |
| No valid images | `No usable images. Provide 4-8 valid image files` |
| Corrupt / missing image file | Skipped with warning; video still made |
| < 4 images | Warning; photos are reused across scenes |
| > 8 images / > 5 features | Extra ones ignored with warning |
| No features / no contact | Warning; feature scenes dropped / generic CTA |
| Invalid JSON | Message with line number |
| No TTS engine | Video made without voice + warning |
| LLM missing key / error / failed fact-check | Template script + warning |
| ffmpeg failure | `RenderError` message; partial file removed |

## Tests

```bash
pytest -q        # 12 tests: validation, matching, fact-checker, LLM fallback, end-to-end render, CLI exit codes
```

## Limitations

* Voice-over from espeak-ng is robotic; use gTTS (online) or plug a neural TTS into `audio.BACKENDS` for production quality.
* The tool does **not** look at photo content (no vision model). Matching relies on file names; otherwise photos are assigned by least-use. A vision model could classify rooms automatically — a natural next step.
* Fixed visual template (no brand logo/colour theme yet); English narration only; text is not auto-translated.
* Rendering is CPU-only: a ~35 s 720p video took ~75 s on a modest 2-core cloud sandbox (expect less on a modern laptop; 1080p ≈ 2× longer). Use `--fps 15` for quick drafts.
* The claim-word list in the fact-checker is heuristic; it reduces, but cannot mathematically eliminate, subtle LLM embellishment — which is why template mode is the default.

## Suggested 2-minute demo flow

1. `streamlit run app.py` → tick **Use sample property** → *Generate* → play/download.
2. Untick sample, press *Generate* with an empty form → show friendly errors.
3. Upload only 2 photos + one corrupt file → show warnings but a finished video.
4. Run `pytest -q` and show the hallucination-fallback test.
5. Open `output/sample_video_portrait.mp4` to show the Reels format.
