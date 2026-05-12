# ============================================================
# PathshalaAI — Auto-Dub Educational Lectures
# Hackathon Demo · Powered by Sarvam AI
#
# Pipeline:
#   Stage 1 — Saaras v3        : Audio → English transcript
#   Stage 2 — Sarvam-Translate : English → Target language subtitles
#   Stage 3 — Mayura v1        : English → Colloquial study notes
#   Stage 4 — Bulbul v2 TTS    : Translated subtitles → Audio
# ============================================================

import io
import base64
import time
import math
import streamlit as st
import requests
from pydub import AudioSegment

from SARVAM_TRANSLATE_OP import run_translation, LANGUAGES, COST_PER_10K
from mayura import run_mayura_chunked

# ── Constants ─────────────────────────────────────────────────
SAARAS_API_URL  = "https://api.sarvam.ai/speech-to-text"
SAARAS_MODEL    = "saaras:v3"
TTS_API_URL     = "https://api.sarvam.ai/text-to-speech"
REQUEST_TIMEOUT = 120
MAX_AUDIO_SEC   = 25

DUB_LANGUAGES: dict[str, dict] = {
    "hi-IN": {"name": "हिन्दी",  "english": "Hindi",     "flag": "🇮🇳", "speaker": "vidya"},
    "ta-IN": {"name": "தமிழ்",   "english": "Tamil",     "flag": "🏛️", "speaker": "vidya"},
    "te-IN": {"name": "తెలుగు",  "english": "Telugu",    "flag": "🌿", "speaker": "meera"},
    "bn-IN": {"name": "বাংলা",    "english": "Bengali",   "flag": "🐯", "speaker": "arvind"},
    "mr-IN": {"name": "मराठी",   "english": "Marathi",   "flag": "🦁", "speaker": "arvind"},
    "gu-IN": {"name": "ગુજરાતી", "english": "Gujarati",  "flag": "🦚", "speaker": "arvind"},
    "kn-IN": {"name": "ಕನ್ನಡ",   "english": "Kannada",   "flag": "🐘", "speaker": "meera"},
    "ml-IN": {"name": "മലയാളം",  "english": "Malayalam", "flag": "🌴", "speaker": "meera"},
    "od-IN": {"name": "ଓଡ଼ିଆ",   "english": "Odia",      "flag": "🪷", "speaker": "arvind"},
    "pa-IN": {"name": "ਪੰਜਾਬੀ",  "english": "Punjabi",   "flag": "🌾", "speaker": "arvind"},
}

SUBJECTS = {
    "physics":   "⚛️ Physics",
    "chemistry": "🧪 Chemistry",
    "biology":   "🌱 Biology",
    "maths":     "📐 Mathematics",
    "history":   "📜 History",
    "geography": "🌍 Geography",
    "civics":    "⚖️ Civics",
    "economics": "📊 Economics",
    "english":   "📖 English Literature",
    "other":     "📚 Other",
}

st.set_page_config(
    page_title="PathshalaAI — Dub Every Lecture",
    page_icon="🎓",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&family=Noto+Sans+Devanagari:wght@400;600&display=swap');

:root {
    --bg:         #0d1117;
    --surface:    #161b22;
    --surface2:   #21262d;
    --border:     #30363d;
    --text:       #e6edf3;
    --muted:      #7d8590;
    --green:      #3fb950;
    --blue:       #58a6ff;
    --purple:     #bc8cff;
    --orange:     #ffa657;
    --red:        #f85149;
    --gold:       #d29922;
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    background: var(--bg) !important;
    color: var(--text) !important;
}

.hero {
    background: linear-gradient(135deg, #0d1117 0%, #1a1f2e 50%, #0d1117 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 32px 36px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--green), var(--blue), var(--purple));
}
.hero::after {
    content: '🎓';
    position: absolute;
    right: 32px; top: 50%;
    transform: translateY(-50%);
    font-size: 5rem;
    opacity: 0.06;
}
.hero h1 {
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    background: linear-gradient(90deg, var(--green), var(--blue));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 6px !important;
}
.hero .sub { color: var(--muted); font-size: 0.95rem; }

.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-family: 'Space Mono', monospace;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}
.badge-saaras { background: #0d4429; color: var(--green);  border: 1px solid #238636; }
.badge-sarvam { background: #0c2d6b; color: var(--blue);   border: 1px solid #1f6feb; }
.badge-mayura { background: #2d1b69; color: var(--purple); border: 1px solid #6e40c9; }
.badge-tts    { background: #3d1f00; color: var(--gold);   border: 1px solid #9e6a03; }

.pipeline-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin: 16px 0;
}
.pipeline-node {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.8rem;
    text-align: center;
    min-width: 100px;
}
.pipeline-node .icon  { font-size: 1.2rem; display: block; margin-bottom: 2px; }
.pipeline-node .label { font-family: 'Space Mono', monospace; font-size: 0.62rem; color: var(--muted); }
.pipeline-arrow { color: var(--green); font-size: 1.2rem; }

.stats-row { display: flex; gap: 10px; margin: 16px 0; }
.stat-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    flex: 1;
    text-align: center;
}
.stat-box .num { font-size: 1.6rem; font-weight: 700; color: var(--blue); line-height: 1; }
.stat-box .lbl {
    font-family: 'Space Mono', monospace;
    font-size: 0.62rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 4px;
}

.tts-result {
    background: linear-gradient(135deg, #0d2818, #0d1117);
    border: 1px solid #238636;
    border-radius: 10px;
    padding: 20px 24px;
    text-align: center;
}
.tts-result .tts-lang { font-size: 1.4rem; margin-bottom: 8px; }
.tts-result .tts-note {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
    color: var(--green);
    letter-spacing: 0.06em;
}

.subtitle-card {
    background: var(--surface2);
    border-left: 3px solid var(--blue);
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin: 8px 0;
    font-family: 'Noto Sans Devanagari', 'Plus Jakarta Sans', sans-serif;
    font-size: 1.05rem;
    line-height: 1.7;
    color: var(--text);
}

.note-card {
    background: var(--surface2);
    border-left: 3px solid var(--purple);
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin: 8px 0;
    font-family: 'Noto Sans Devanagari', 'Plus Jakarta Sans', sans-serif;
    font-size: 1rem;
    line-height: 1.7;
    color: var(--text);
}

.chunk-info {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    margin: 8px 0;
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem;
    color: var(--muted);
}

section[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text) !important; }

.stButton > button {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #238636, #2ea043) !important;
    border: none !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2ea043, #3fb950) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stExpander"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}
.stTextArea textarea {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.82rem !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
st.session_state.setdefault("transcript",      "")
st.session_state.setdefault("subtitles",       {})
st.session_state.setdefault("study_notes",     {})
st.session_state.setdefault("tts_audio",       {})
st.session_state.setdefault("pipeline_log",    [])
st.session_state.setdefault("source_filename", "")
st.session_state.setdefault("total_chars",     0)
st.session_state.setdefault("chunk_count",     0)
st.session_state.setdefault("run_subtitles",   False)
st.session_state.setdefault("run_tts",         False)


# ═══════════════════════════════════════════════════════════════
# API FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def chunk_audio(audio_bytes: bytes, filename: str, chunk_sec: int = MAX_AUDIO_SEC) -> list[tuple[bytes, str]]:
    ext = filename.rsplit(".", 1)[-1].lower()
    fmt = "mp4" if ext in ("m4a", "aac") else ext
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
    chunk_ms = chunk_sec * 1000
    chunks = []
    for i, start in enumerate(range(0, len(seg), chunk_ms)):
        part = seg[start: start + chunk_ms]
        buf  = io.BytesIO()
        part.export(buf, format="wav")
        chunks.append((buf.getvalue(), f"chunk_{i:03d}.wav"))
    return chunks


def transcribe_chunk(chunk_bytes: bytes, chunk_name: str, source_lang: str, api_key: str) -> tuple[str, str]:
    files = {"file": (chunk_name, io.BytesIO(chunk_bytes), "audio/wav")}
    data  = {"model": SAARAS_MODEL, "mode": "translate"}
    if source_lang and source_lang != "unknown":
        data["language_code"] = source_lang
    resp = requests.post(
        SAARAS_API_URL,
        headers={"api-subscription-key": api_key},
        files=files,
        data=data,
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        try:    err = resp.json()
        except: err = resp.text[:400]
        raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}: {err}", response=resp)
    result = resp.json()
    text = (
        result.get("transcript") or result.get("text")
        or result.get("translated_text") or result.get("output") or ""
    ).strip()
    detected = result.get("language_code", source_lang or "unknown")
    return text, detected


def stt_to_english(audio_bytes: bytes, filename: str, source_lang: str,
                   api_key: str, progress_callback=None) -> tuple[str, str]:
    chunks = chunk_audio(audio_bytes, filename)
    total  = len(chunks)
    st.session_state["chunk_count"] = total
    transcripts = []
    detected    = source_lang or "unknown"
    for i, (chunk_bytes, chunk_name) in enumerate(chunks):
        if progress_callback:
            progress_callback(i / total, f"Transcribing chunk {i+1}/{total}…")
        text, lang = transcribe_chunk(chunk_bytes, chunk_name, source_lang, api_key)
        if text:
            transcripts.append(text)
        if detected == "unknown" and lang != "unknown":
            detected = lang
    if progress_callback:
        progress_callback(1.0, f"Done — {total} chunk(s) transcribed.")
    if not transcripts:
        raise ValueError("No transcript returned for any audio chunk.")
    return " ".join(transcripts), detected


def call_tts_api(text: str, target_lang: str, api_key: str) -> bytes | None:
    """Bulbul v2 TTS — chunked to 500 chars, joined."""
    lang_info   = DUB_LANGUAGES.get(target_lang, {})
    speaker     = lang_info.get("speaker", "arvind")
    chunks      = [text[i:i+500] for i in range(0, len(text), 500)]
    audio_parts = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        resp = requests.post(
            TTS_API_URL,
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "inputs":               [chunk],
                "target_language_code": target_lang,
                "speaker":              speaker,
                "model":                "bulbul:v2",   # v1 deprecated Apr 30 2025
            },
            timeout=30,
        )
        if not resp.ok:
            try:    err = resp.json()
            except: err = resp.text[:300]
            raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}: {err}", response=resp)
        audios = resp.json().get("audios", [])
        if audios:
            audio_parts.append(base64.b64decode(audios[0]))
    return b"".join(audio_parts) if audio_parts else None


def log_stage(stage: str, model: str, preview: str):
    st.session_state["pipeline_log"].append({
        "stage":   stage,
        "model":   model,
        "preview": preview[:100] + ("…" if len(preview) > 100 else ""),
        "time":    time.strftime("%H:%M:%S"),
    })


# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🎓 PathshalaAI")
    st.markdown("---")

    api_key: str = st.text_input("SARVAM API KEY", type="password", placeholder="Paste your key…")
    st.caption("[Get key → sarvam.ai](https://sarvam.ai/)")

    st.markdown("---")
    st.markdown("**LECTURE LANGUAGE**")
    source_lang = st.selectbox(
        "Language spoken in lecture",
        options=["unknown", "en-IN", "hi-IN"],
        format_func=lambda k: {"unknown": "🔍 Auto Detect", "en-IN": "English", "hi-IN": "Hindi"}[k],
        label_visibility="collapsed",
    )

    st.markdown("**TARGET LANGUAGES**")
    target_langs = st.multiselect(
        "Dub into (select up to 4)",
        options=list(DUB_LANGUAGES.keys()),
        default=["hi-IN", "ta-IN"],
        format_func=lambda k: f"{DUB_LANGUAGES[k]['flag']} {DUB_LANGUAGES[k]['english']}",
        max_selections=4,
        label_visibility="collapsed",
    )

    st.markdown("**SUBJECT**")
    subject = st.selectbox(
        "Lecture subject",
        options=list(SUBJECTS.keys()),
        format_func=lambda k: SUBJECTS[k],
        label_visibility="collapsed",
    )

    st.markdown("**SPEAKER GENDER**")
    speaker_gender = st.radio("Teacher gender", options=["Male", "Female"], horizontal=True, label_visibility="collapsed")

    enable_study_notes = st.toggle("📝 Generate study notes (Mayura)", value=True)

    st.markdown("---")
    st.markdown("**MODEL STACK**")
    st.markdown("""
    <span class='badge badge-saaras'>Saaras v3</span> Transcription<br><br>
    <span class='badge badge-sarvam'>Sarvam-Translate</span> Subtitles<br><br>
    <span class='badge badge-mayura'>Mayura v1</span> Study Notes<br><br>
    <span class='badge badge-tts'>Bulbul v2</span> Audio Generation
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.session_state["transcript"]:
        st.metric("Transcript chars", len(st.session_state["transcript"]))
    if st.session_state["chunk_count"]:
        st.metric("Audio chunks", st.session_state["chunk_count"])
    if st.session_state["tts_audio"]:
        st.metric("Languages voiced", len(st.session_state["tts_audio"]))
    if st.session_state["total_chars"]:
        cost = (st.session_state["total_chars"] / 10_000) * COST_PER_10K
        st.metric("Est. cost", f"₹{cost:.3f}")

    st.markdown("---")
    if st.button("🔄 Reset All", use_container_width=True):
        for k in ["transcript", "subtitles", "study_notes", "tts_audio",
                  "pipeline_log", "source_filename", "total_chars", "chunk_count",
                  "run_subtitles", "run_tts"]:
            st.session_state[k] = (
                {} if k in ["subtitles", "study_notes", "tts_audio"]
                else [] if k == "pipeline_log"
                else 0  if k in ["total_chars", "chunk_count"]
                else False if k in ["run_subtitles", "run_tts"]
                else ""
            )
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# MAIN UI
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<div class='hero'>
    <h1>PathshalaAI — पाठशाला AI</h1>
    <div class='sub'>
        Auto-Dub Every Lecture · Every Indian Language · Powered by Sarvam AI
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='pipeline-row'>
    <div class='pipeline-node'><span class='icon'>🎙️</span><span>Lecture Audio</span><span class='label'>INPUT</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>✂️</span><span>Auto-Chunk</span><span class='label'>25s SPLITS</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>📝</span><span>Saaras v3</span><span class='label'>TRANSCRIPT</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>🌐</span><span>Sarvam-Translate</span><span class='label'>SUBTITLES</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>🗣️</span><span>Mayura v1</span><span class='label'>STUDY NOTES</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>🔊</span><span>Bulbul v2</span><span class='label'>AUDIO</span></div>
    <span class='pipeline-arrow'>→</span>
    <div class='pipeline-node'><span class='icon'>🎧</span><span>Dubbed Audio</span><span class='label'>OUTPUT</span></div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─────────────────────────────────────────────────────────────
# STAGE 1
# ─────────────────────────────────────────────────────────────
st.markdown("### 🎙️ Stage 1 — Upload Lecture Audio")
st.markdown(
    "<span class='badge badge-saaras'>Saaras v3 · translate mode · auto-chunked</span> &nbsp;"
    "Lecture audio → English transcript · any duration supported",
    unsafe_allow_html=True,
)
st.caption("No duration limit · audio auto-split into 25s chunks · wav, mp3, ogg, flac, aac, m4a, webm")

input_method = st.radio("Input method", ["📁 Upload file", "🎤 Record live"], horizontal=True, label_visibility="collapsed")

audio_bytes    = None
audio_filename = "lecture.wav"

if input_method == "📁 Upload file":
    uploaded = st.file_uploader("Upload lecture audio", type=["wav","mp3","ogg","flac","aac","m4a","webm"], label_visibility="collapsed")
    if uploaded:
        audio_bytes    = uploaded.read()
        audio_filename = uploaded.name
        ext = audio_filename.rsplit(".", 1)[-1]
        st.audio(audio_bytes, format=f"audio/{ext}")
        try:
            fmt = "mp4" if ext in ("m4a", "aac") else ext
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
            duration_sec = len(seg) / 1000
            chunk_count  = math.ceil(duration_sec / MAX_AUDIO_SEC)
            st.markdown(
                f"<div class='chunk-info'>📎 {audio_filename} · {len(audio_bytes):,} bytes · "
                f"⏱️ {duration_sec:.1f}s · ✂️ Will split into {chunk_count} chunk(s) of ≤{MAX_AUDIO_SEC}s</div>",
                unsafe_allow_html=True,
            )
        except Exception:
            st.caption(f"`{audio_filename}` · {len(audio_bytes):,} bytes")
else:
    recorded = st.audio_input("Record lecture audio", label_visibility="collapsed")
    if recorded:
        audio_bytes    = recorded.read()
        audio_filename = "recorded.wav"
        st.audio(audio_bytes)
        st.caption(f"Recorded · {len(audio_bytes):,} bytes")

col1, col2 = st.columns(2)
with col1:
    btn_transcribe = st.button(
        "📝 Transcribe Lecture (Saaras v3)", type="primary",
        use_container_width=True,
        disabled=not api_key or audio_bytes is None,
    )
with col2:
    if st.session_state["transcript"]:
        st.success("✅ Stage 1 complete")

if not api_key:
    st.caption("⬅️ Add Sarvam API key in sidebar.")
elif audio_bytes is None:
    st.caption("⬆️ Upload or record lecture audio first.")

if btn_transcribe and audio_bytes and api_key:
    progress_bar = st.progress(0, text="Preparing audio chunks…")
    def update_progress(pct: float, msg: str):
        progress_bar.progress(pct, text=msg)
    try:
        transcript, detected = stt_to_english(audio_bytes, audio_filename, source_lang, api_key, update_progress)
        progress_bar.progress(1.0, text="✅ Transcription complete!")
        st.session_state["transcript"]      = transcript
        st.session_state["source_filename"] = audio_filename
        st.session_state["total_chars"]    += len(transcript)
        log_stage("Stage 1 · Transcript", "Saaras v3", transcript)
        st.success(
            f"✅ Transcribed {st.session_state['chunk_count']} chunk(s) · "
            f"Detected: **{detected}** · {len(transcript):,} chars"
        )
        st.rerun()
    except Exception as e:
        progress_bar.empty()
        st.error(f"❌ Transcription failed: {e}")

if st.session_state["transcript"]:
    with st.expander("📄 Stage 1 Result — English Transcript", expanded=True):
        edited = st.text_area("Edit transcript if needed", value=st.session_state["transcript"],
                              height=160, key="transcript_edit", label_visibility="collapsed")
        if edited != st.session_state["transcript"]:
            if st.button("💾 Save edits"):
                st.session_state["transcript"] = edited
                st.rerun()
        st.download_button("📥 Download Transcript", data=st.session_state["transcript"],
                           file_name="transcript_en.txt", mime="text/plain")

st.markdown("---")

# ─────────────────────────────────────────────────────────────
# STAGE 2
# ─────────────────────────────────────────────────────────────
st.markdown("### 🌐 Stage 2 — Generate Subtitles")
st.markdown(
    "<span class='badge badge-sarvam'>Sarvam-Translate v1 · formal mode</span> &nbsp;"
    "English transcript → subtitles in all target languages",
    unsafe_allow_html=True,
)

if not st.session_state["subtitles"]:
    if st.button(
        "🌐 Generate Subtitles (Sarvam-Translate)", type="primary",
        use_container_width=True,
        disabled=not api_key or not st.session_state["transcript"] or not target_langs,
        key="btn_subtitles",
    ):
        st.session_state["run_subtitles"] = True

if st.session_state.get("run_subtitles") and not st.session_state["subtitles"]:
    st.session_state["run_subtitles"] = False
    with st.spinner(f"Sarvam-Translate → {len(target_langs)} languages…"):
        try:
            results = run_translation(
                st.session_state["transcript"],
                target_langs,
                speaker_gender,
                "formal",
                "international",
                api_key,
            )
            success = {k: v for k, v in results.items() if isinstance(v, str)}
            errors  = {k: v for k, v in results.items() if isinstance(v, Exception)}
            st.session_state["subtitles"]    = success
            st.session_state["total_chars"] += sum(len(v) for v in success.values())
            for lang, text in success.items():
                log_stage(f"Stage 2 · Subtitles · {DUB_LANGUAGES[lang]['english']}", "Sarvam-Translate v1", text)
            for lang, err in errors.items():
                st.warning(f"⚠️ {DUB_LANGUAGES.get(lang, {}).get('english', lang)}: {err}")
            st.success(f"✅ Subtitles ready for {len(success)} languages!")
        except Exception as e:
            st.error(f"❌ Stage 2 failed: {e}")

if st.session_state["subtitles"]:
    st.success(f"✅ Stage 2 complete · {len(st.session_state['subtitles'])} languages")
    with st.expander("📖 Stage 2 Result — Subtitles", expanded=True):
        tabs = st.tabs([f"{DUB_LANGUAGES[k]['flag']} {DUB_LANGUAGES[k]['english']}" for k in st.session_state["subtitles"]])
        for tab, (lang, text) in zip(tabs, st.session_state["subtitles"].items()):
            with tab:
                st.markdown(f"<div class='subtitle-card'>{text}</div>", unsafe_allow_html=True)
                st.download_button(f"📥 Download {DUB_LANGUAGES[lang]['english']} subtitles",
                                   data=text, file_name=f"subtitles_{lang}.txt",
                                   mime="text/plain", key=f"dl_sub_{lang}")

st.markdown("---")

# ─────────────────────────────────────────────────────────────
# STAGE 3
# ─────────────────────────────────────────────────────────────
if enable_study_notes:
    st.markdown("### 📝 Stage 3 — Study Notes")
    st.markdown(
        "<span class='badge badge-mayura'>Mayura v1 · colloquial mode</span> &nbsp;"
        "English transcript → plain-language study notes for students",
        unsafe_allow_html=True,
    )

    MAYURA_SUPPORTED = {"hi-IN","bn-IN","ta-IN","te-IN","mr-IN","gu-IN","kn-IN","ml-IN","od-IN","pa-IN","ur-IN"}
    mayura_targets = [l for l in target_langs if l in MAYURA_SUPPORTED]
    unsupported    = [l for l in target_langs if l not in MAYURA_SUPPORTED]

    if unsupported:
        st.caption(f"ℹ️ Mayura doesn't support: {', '.join(DUB_LANGUAGES.get(l,{}).get('english',l) for l in unsupported)}")

    btn_notes = st.button(
        "📝 Generate Study Notes (Mayura)", type="primary",
        use_container_width=True,
        disabled=not api_key or not st.session_state["transcript"] or not mayura_targets,
    )

    if st.session_state["study_notes"]:
        st.success(f"✅ Stage 3 complete · {len(st.session_state['study_notes'])} languages")

    if btn_notes and st.session_state["transcript"] and mayura_targets:
        with st.spinner(f"Mayura v1 · Colloquial → {len(mayura_targets)} languages…"):
            notes_result = {}
            for lang in mayura_targets:
                try:
                    note = run_mayura_chunked(
                        st.session_state["transcript"], lang,
                        speaker_gender, "colloquial", "international", api_key,
                    )
                    notes_result[lang] = note
                    st.session_state["total_chars"] += len(note)
                    log_stage(f"Stage 3 · Notes · {DUB_LANGUAGES[lang]['english']}", "Mayura v1", note)
                except Exception as e:
                    st.warning(f"⚠️ Notes failed for {DUB_LANGUAGES.get(lang,{}).get('english',lang)}: {e}")
            st.session_state["study_notes"] = notes_result
            st.success(f"✅ Study notes ready for {len(notes_result)} languages!")
            st.rerun()

    if st.session_state["study_notes"]:
        with st.expander("🗣️ Stage 3 Result — Study Notes", expanded=True):
            tabs = st.tabs([f"{DUB_LANGUAGES[k]['flag']} {DUB_LANGUAGES[k]['english']}" for k in st.session_state["study_notes"]])
            for tab, (lang, text) in zip(tabs, st.session_state["study_notes"].items()):
                with tab:
                    st.markdown(f"<div class='note-card'>{text}</div>", unsafe_allow_html=True)
                    st.download_button(f"📥 Download {DUB_LANGUAGES[lang]['english']} notes",
                                       data=text, file_name=f"notes_{lang}.txt",
                                       mime="text/plain", key=f"dl_note_{lang}")

    st.markdown("---")

# ─────────────────────────────────────────────────────────────
# STAGE 4 — Bulbul v2 TTS (primary, no dub)
# ─────────────────────────────────────────────────────────────
st.markdown("### 🔊 Stage 4 — Generate Audio (Bulbul v2 TTS)")
st.markdown(
    "<span class='badge badge-tts'>Bulbul v2 · TTS</span> &nbsp;"
    "Translated subtitles → natural audio in each language",
    unsafe_allow_html=True,
)
st.caption("ℹ️ Runs Stage 2 subtitles through Bulbul v2 TTS. Run Stage 2 first.")

if not st.session_state["tts_audio"]:
    if st.button(
        "🔊 Generate Audio (Bulbul v2)", type="primary",
        use_container_width=True,
        disabled=not api_key or not st.session_state["subtitles"],
        key="btn_tts",
    ):
        st.session_state["run_tts"] = True

if st.session_state.get("run_tts") and not st.session_state["tts_audio"]:
    st.session_state["run_tts"] = False
    tts_results = {}
    subtitles   = st.session_state["subtitles"]
    progress    = st.progress(0, text="Starting audio generation…")

    for i, lang in enumerate(target_langs):
        lang_name = DUB_LANGUAGES[lang]["english"]
        progress.progress(i / len(target_langs), text=f"Generating audio → {lang_name}…")

        tts_text = subtitles.get(lang, "")
        if not tts_text:
            st.warning(f"⚠️ No subtitle text for {lang_name} — run Stage 2 first.")
            continue

        try:
            with st.spinner(f"🔊 Bulbul v2 → {lang_name}…"):
                tts_bytes = call_tts_api(tts_text, lang, api_key)
            if tts_bytes:
                tts_results[lang] = tts_bytes
                log_stage(f"Stage 4 · TTS · {lang_name}", "Bulbul v2", f"{len(tts_bytes):,} bytes")
                st.success(f"✅ {lang_name} audio generated!")
            else:
                st.error(f"❌ Empty audio returned for {lang_name}")
        except Exception as e:
            st.error(f"❌ TTS failed for {lang_name}: {e}")

    progress.progress(1.0, text="All audio generated!")
    st.session_state["tts_audio"] = tts_results

if st.session_state["tts_audio"]:
    st.success(f"✅ Stage 4 complete · {len(st.session_state['tts_audio'])} language(s)")
    with st.expander("🎧 Stage 4 Result — Generated Audio", expanded=True):
        tabs = st.tabs([
            f"{DUB_LANGUAGES[k]['flag']} {DUB_LANGUAGES[k]['english']}"
            for k in st.session_state["tts_audio"]
        ])
        for tab, (lang, audio_data) in zip(tabs, st.session_state["tts_audio"].items()):
            with tab:
                lang_info = DUB_LANGUAGES[lang]
                st.markdown(f"""
                <div class='tts-result'>
                    <div class='tts-lang'>{lang_info['flag']} {lang_info['name']}</div>
                    <div class='tts-note'>🔊 BULBUL v2 TTS &nbsp;·&nbsp; {len(audio_data):,} bytes</div>
                </div>
                """, unsafe_allow_html=True)
                st.audio(audio_data, format="audio/wav")
                st.download_button(
                    f"📥 Download {lang_info['english']} audio",
                    data=audio_data,
                    file_name=f"audio_{lang}.wav",
                    mime="audio/wav",
                    key=f"dl_tts_{lang}",
                    use_container_width=True,
                )

st.markdown("---")

# ─────────────────────────────────────────────────────────────
# FULL PACKAGE DOWNLOAD
# ─────────────────────────────────────────────────────────────
if st.session_state["transcript"] and (st.session_state["subtitles"] or st.session_state["study_notes"]):
    st.markdown("### 📦 Full Package")
    package_lines = [
        "=" * 60,
        "PathshalaAI — Lecture Package",
        f"Subject: {SUBJECTS[subject]}",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60, "",
        "── ENGLISH TRANSCRIPT ──",
        st.session_state["transcript"], "",
    ]
    for lang, text in st.session_state["subtitles"].items():
        package_lines += [f"── SUBTITLES · {DUB_LANGUAGES[lang]['english'].upper()} ──", text, ""]
    for lang, text in st.session_state["study_notes"].items():
        package_lines += [f"── STUDY NOTES · {DUB_LANGUAGES[lang]['english'].upper()} ──", text, ""]
    st.download_button(
        "📦 Download Full Text Package (.txt)",
        data="\n".join(package_lines),
        file_name=f"pathshala_{subject}_{int(time.time())}.txt",
        mime="text/plain",
        use_container_width=True,
    )
    st.markdown("---")

# ─────────────────────────────────────────────────────────────
# PIPELINE AUDIT LOG
# ─────────────────────────────────────────────────────────────
if st.session_state["pipeline_log"]:
    with st.expander("🔍 Pipeline Audit Log", expanded=False):
        for entry in st.session_state["pipeline_log"]:
            badge_class = (
                "badge-saaras" if "Saaras"  in entry["model"] else
                "badge-mayura" if "Mayura"  in entry["model"] else
                "badge-tts"    if "Bulbul"  in entry["model"] else
                "badge-sarvam"
            )
            st.markdown(
                f"<span style='font-family:monospace;font-size:0.75rem;color:#7d8590;'>{entry['time']}</span> &nbsp;"
                f"**{entry['stage']}** &nbsp;"
                f"<span class='badge {badge_class}'>{entry['model']}</span><br>"
                f"<small style='color:#7d8590;'>{entry['preview']}</small>",
                unsafe_allow_html=True,
            )
            st.divider()

# ─────────────────────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────────────────────
if st.session_state["total_chars"] > 0:
    cost = (st.session_state["total_chars"] / 10_000) * COST_PER_10K
    st.markdown(f"""
    <div class='stats-row'>
        <div class='stat-box'><div class='num'>{len(st.session_state.get("subtitles",{}))}</div><div class='lbl'>Languages translated</div></div>
        <div class='stat-box'><div class='num'>{len(st.session_state.get("tts_audio",{}))}</div><div class='lbl'>Languages voiced</div></div>
        <div class='stat-box'><div class='num'>{st.session_state["total_chars"]:,}</div><div class='lbl'>Chars processed</div></div>
        <div class='stat-box'><div class='num'>₹{cost:.3f}</div><div class='lbl'>Est. API cost</div></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.caption("**PathshalaAI** — पाठशाला AI\n\nAuto-Dub Every Lecture · Hackathon Demo")
with col_f2:
    st.caption("Saaras v3 · Sarvam-Translate v1\n\nMayura v1 · Bulbul v2")
with col_f3:
    st.caption(f"Audio sent to Sarvam API only\n\n₹{COST_PER_10K} per 10,000 chars")