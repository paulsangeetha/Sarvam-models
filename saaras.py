# ============================================================
# KISAANVAANI — Saaras v3 Voice Intelligence Dashboard
# Stage 0 of the NyayaSetu pipeline
#
# This file is the VOICE FRONT DOOR for the full system:
#
#   saaras_op.py          ← YOU ARE HERE (voice input)
#       │
#       ▼
#   mayura_op functions   ← colloquial explanation
#       │
#       ▼
#   sarvam_translate_op   ← formal translation / legal draft
#
# API facts (verified from docs):
#   - Endpoint : POST https://api.sarvam.ai/speech-to-text
#   - Model    : saaras:v3
#   - Mode     : "translate"  → speech → English text
#              : "transcribe" → speech → same language text
#   - Max audio: 30 seconds per request
#   - Format   : multipart/form-data  (NOT JSON)
#   - Audio    : wav / mp3 / ogg / flac / aac / m4a
#   - Auto language detection supported
# ============================================================

import io
import hashlib
import tempfile
import concurrent.futures
import streamlit as st
import requests

# ── Import from existing pipeline files ──────────────────────
# Matches your actual filenames on disk
from SARVAM_TRANSLATE_OP import (
    run_translation,
    LANGUAGES,
    MODES,
    BETA_LANGS,
    SOURCE_LANG,
    MAX_WORKERS,
    COST_PER_10K,
)
from mayura import (
    run_mayura_chunked,
    build_legal_draft,
    DOC_TYPES,
)

# MAYURA_SUPPORTED is defined in mayura_op but not exported —
# redefined here to avoid circular import issues
MAYURA_SUPPORTED: dict[str, str] = {
    k: v for k, v in LANGUAGES.items() if k in {
        "hi-IN", "bn-IN", "ta-IN", "te-IN",
        "mr-IN", "gu-IN", "kn-IN", "ml-IN",
        "od-IN", "pa-IN", "ur-IN",
    }
}

# ── Saaras Constants ──────────────────────────────────────────
SAARAS_API_URL   = "https://api.sarvam.ai/speech-to-text"
SAARAS_MODEL     = "saaras:v3"
REQUEST_TIMEOUT  = 60
MAX_AUDIO_SEC    = 30     # hard API limit per request

# Languages Saaras v3 supports (auto-detect also available)
SAARAS_LANGUAGES: dict[str, str] = {
    "unknown": "🔍 Auto Detect",
    "hi-IN":   "हिन्दी (Hindi)",
    "bn-IN":   "বাংলা (Bengali)",
    "ta-IN":   "தமிழ் (Tamil)",
    "te-IN":   "తెలుగు (Telugu)",
    "mr-IN":   "मराठी (Marathi)",
    "gu-IN":   "ગુજરાતી (Gujarati)",
    "kn-IN":   "ಕನ್ನಡ (Kannada)",
    "ml-IN":   "മലയാളം (Malayalam)",
    "od-IN":   "ଓଡ଼ିଆ (Odia)",
    "pa-IN":   "ਪੰਜਾਬੀ (Punjabi)",
    "en-IN":   "English (Indian)",
}

SAARAS_MODES = {
    "translate":  "🌐 Translate → English  (speech in any Indian language → English text)",
    "transcribe": "📝 Transcribe           (speech → same language text)",
    "verbatim":   "🎙️ Verbatim             (exact word-for-word, no normalization)",
    "codemix":    "💬 Code-Mixed           (mixed language output)",
}

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="KisaanVaani — Voice to Legal Aid",
    page_icon="🎙️",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    .model-badge-saaras {
        background: #065f46;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .model-badge-sarvam {
        background: #0f4c81;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .model-badge-mayura {
        background: #7c3aed;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .pipeline-step {
        background: #1e293b;
        border-left: 4px solid #10b981;
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.88rem;
        color: #e2e8f0;
    }
    .step-arrow { text-align: center; color: #10b981; font-size: 1.2rem; }
    .audio-note {
        background: #1c1917;
        border: 1px solid #44403c;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.82rem;
        color: #a8a29e;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
st.session_state.setdefault("transcribed_text", "")
st.session_state.setdefault("detected_language", "")
st.session_state.setdefault("saaras_mode_used", "")
st.session_state.setdefault("colloquial_out", "")
st.session_state.setdefault("formal_translation_out", "")
st.session_state.setdefault("legal_draft_out", "")
st.session_state.setdefault("pipeline_log", [])

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    api_key: str = st.text_input(
        "Sarvam API Key",
        type="password",
        placeholder="Paste your key here…",
        help="Same key works for Saaras, Mayura, and Sarvam-Translate.",
    )
    st.caption("Get your key at [sarvam.ai](https://sarvam.ai/)")

    st.markdown("---")
    st.subheader("🎙️ Saaras Settings")

    source_lang = st.selectbox(
        "Spoken language",
        options=list(SAARAS_LANGUAGES.keys()),
        format_func=lambda c: SAARAS_LANGUAGES[c],
        index=0,
        help="Select 'Auto Detect' if unsure — Saaras will identify the language.",
    )

    saaras_mode = st.radio(
        "Output mode",
        options=list(SAARAS_MODES.keys()),
        format_func=lambda k: SAARAS_MODES[k],
        index=0,
        help="Use 'Translate → English' for the full NyayaSetu pipeline.",
    )

    st.markdown("---")
    st.subheader("👤 Citizen Profile")

    citizen_lang = st.selectbox(
        "Translate response into",
        options=list(MAYURA_SUPPORTED.keys()),
        format_func=lambda c: MAYURA_SUPPORTED[c],
        index=0,
        help="Language for Mayura colloquial explanation.",
    )

    speaker_gender = st.radio(
        "Speaker gender",
        options=["Male", "Female"],
        horizontal=True,
    )

    use_native_numerals = st.toggle("Native numerals", value=False)

    doc_type = st.selectbox(
        "Document type",
        options=list(DOC_TYPES.keys()),
        format_func=lambda k: DOC_TYPES[k],
    )

    st.markdown("---")
    st.subheader("🔬 Model Stack")
    st.markdown("""
    <span class='model-badge-saaras'>Saaras v3</span> Voice → English<br><br>
    <span class='model-badge-mayura'>Mayura v1</span> Colloquial explanation<br><br>
    <span class='model-badge-sarvam'>Sarvam-Translate v1</span> Formal translation
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 Reset Pipeline", use_container_width=True):
        for k in ["transcribed_text", "detected_language", "saaras_mode_used",
                  "colloquial_out", "formal_translation_out",
                  "legal_draft_out", "pipeline_log"]:
            st.session_state[k] = [] if k == "pipeline_log" else ""
        st.rerun()

# ── Saaras API call ───────────────────────────────────────────
def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    lang_code: str,
    mode: str,
    key: str,
) -> tuple[str, str]:
    """
    Sends audio to Saaras v3 via multipart/form-data.
    Returns (transcribed_text, detected_language_code).

    NOTE: Saaras uses multipart/form-data — NOT JSON.
    All fields are form fields, audio is a file upload.
    """
    # Determine file MIME type from extension
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {
        "wav":  "audio/wav",
        "mp3":  "audio/mpeg",
        "ogg":  "audio/ogg",
        "flac": "audio/flac",
        "aac":  "audio/aac",
        "m4a":  "audio/mp4",
        "webm": "audio/webm",
    }
    mime_type = mime_map.get(ext, "audio/wav")

    # Build multipart form data
    files = {
        "file": (filename, io.BytesIO(audio_bytes), mime_type),
    }
    data = {
        "model":  SAARAS_MODEL,
        "mode":   mode,
    }
    # Only add language if not auto-detect
    if lang_code and lang_code != "unknown":
        data["language_code"] = lang_code

    resp = requests.post(
        SAARAS_API_URL,
        headers={"api-subscription-key": key},  # NO Content-Type — requests sets multipart boundary
        files=files,
        data=data,
        timeout=REQUEST_TIMEOUT,
    )

    # Expose actual error body
    if not resp.ok:
        try:
            err = resp.json()
        except Exception:
            err = resp.text[:400]
        raise requests.exceptions.HTTPError(
            f"HTTP {resp.status_code} — Saaras API error: {err}",
            response=resp,
        )

    result = resp.json()

    # Extract transcript
    transcript = (
        result.get("transcript")
        or result.get("text")
        or result.get("translated_text")
        or result.get("output")
        or ""
    )
    detected_lang = result.get("language_code", lang_code or "unknown")

    if not transcript:
        raise ValueError(
            f"Saaras returned no transcript. Keys: {list(result.keys())} | Full: {result}"
        )

    return transcript.strip(), detected_lang


# ── Header ────────────────────────────────────────────────────
st.title("🎙️ KisaanVaani — किसान वाणी")
st.markdown(
    "**Voice-First Legal & Agricultural Aid** · "
    "Powered by <span class='model-badge-saaras'>Saaras v3</span> + "
    "<span class='model-badge-mayura'>Mayura v1</span> + "
    "<span class='model-badge-sarvam'>Sarvam-Translate v1</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Speak in any Indian language → Transcribed to English → "
    "Explained in your language → Full legal draft generated."
)
st.markdown("---")

# ── Pipeline visual ───────────────────────────────────────────
with st.expander("📊 Full 4-model pipeline", expanded=False):
    st.markdown("""
    <div class='pipeline-step'>
        <b>Stage 0</b> &nbsp;
        <span class='model-badge-saaras'>Saaras v3 · Translate mode</span><br>
        Audio (any Indian language) → English text · Auto language detection
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Stage 1</b> &nbsp;
        <span class='model-badge-sarvam'>Sarvam-Translate v1 · Formal</span><br>
        English text → Citizen's language (formal, accurate)
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Stage 2</b> &nbsp;
        <span class='model-badge-mayura'>Mayura v1 · Colloquial</span><br>
        English → Citizen's language in plain spoken style
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Stage 3</b> &nbsp;
        <span class='model-badge-saaras'>Saaras v3 · Transcribe mode</span> (optional)<br>
        Citizen speaks their reply → transcribed in their language
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Stage 4</b> &nbsp;
        Template + <span class='model-badge-sarvam'>Sarvam-Translate v1</span><br>
        Formal English legal letter generated → ready to submit
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# STAGE 0 — Voice Input → Saaras v3 → English Text
# ══════════════════════════════════════════════════════════════
st.subheader("🎙️ Stage 0 — Voice Input")
st.markdown(
    f"<span class='model-badge-saaras'>Saaras v3 · {saaras_mode}</span>",
    unsafe_allow_html=True,
)

st.markdown("""
<div class='audio-note'>
⚠️ <b>Audio requirements:</b>
Max <b>30 seconds</b> per file · Formats: wav, mp3, ogg, flac, aac, m4a, webm ·
Speak clearly — field noise and accents are handled well by Saaras v3.
</div>
""", unsafe_allow_html=True)

st.markdown("")

# Two input methods — upload or record
input_method = st.radio(
    "Input method",
    options=["📁 Upload audio file", "🎤 Record in browser"],
    horizontal=True,
)

audio_bytes = None
audio_filename = "audio.wav"

if input_method == "📁 Upload audio file":
    uploaded = st.file_uploader(
        "Upload audio file",
        type=["wav", "mp3", "ogg", "flac", "aac", "m4a", "webm"],
        help="Max 30 seconds. Farmer speaking in any Indian language.",
    )
    if uploaded:
        audio_bytes   = uploaded.read()
        audio_filename = uploaded.name
        st.audio(audio_bytes, format=f"audio/{audio_filename.rsplit('.', 1)[-1]}")
        st.caption(f"File: `{audio_filename}` · Size: {len(audio_bytes):,} bytes")

else:
    recorded = st.audio_input(
        "Click to record (max 30 seconds)",
        help="Speak in any Indian language — Saaras will auto-detect.",
    )
    if recorded:
        audio_bytes    = recorded.read()
        audio_filename = "recorded.wav"
        st.audio(audio_bytes)
        st.caption(f"Recorded audio · Size: {len(audio_bytes):,} bytes")

# Transcribe button
col1, col2 = st.columns(2)
with col1:
    btn_transcribe = st.button(
        "🟢 Transcribe / Translate Audio (Saaras v3)",
        type="primary",
        use_container_width=True,
        disabled=not api_key or audio_bytes is None,
    )
with col2:
    if st.session_state["transcribed_text"]:
        detected = st.session_state["detected_language"]
        st.success(f"✅ Done · Detected: {SAARAS_LANGUAGES.get(detected, detected)}")

if not api_key:
    st.caption("⬅️ Add your API key in the sidebar.")
elif audio_bytes is None:
    st.caption("⬆️ Upload or record audio first.")

if btn_transcribe and audio_bytes:
    with st.spinner("Saaras v3 — processing audio…"):
        try:
            transcript, detected_lang = transcribe_audio(
                audio_bytes,
                audio_filename,
                source_lang,
                saaras_mode,
                api_key,
            )
            st.session_state["transcribed_text"]  = transcript
            st.session_state["detected_language"] = detected_lang
            st.session_state["saaras_mode_used"]  = saaras_mode
            st.session_state["pipeline_log"].append({
                "stage": "Stage 0",
                "model": f"Saaras v3 · {saaras_mode}",
                "preview": transcript[:120],
            })
            st.success(
                f"✅ Audio processed · "
                f"Detected language: **{SAARAS_LANGUAGES.get(detected_lang, detected_lang)}**"
            )
            st.rerun()
        except Exception as e:
            st.error(f"❌ Saaras failed: {e}")

# Show Stage 0 result + editable text box
if st.session_state["transcribed_text"]:
    with st.expander("📄 Stage 0 Result — Transcribed / Translated Text", expanded=True):
        st.markdown(
            f"<span class='model-badge-saaras'>Saaras v3 · "
            f"{st.session_state['saaras_mode_used']}</span> &nbsp; "
            f"Detected: <b>{SAARAS_LANGUAGES.get(st.session_state['detected_language'], st.session_state['detected_language'])}</b>",
            unsafe_allow_html=True,
        )
        # Allow manual edit before passing downstream
        edited_text = st.text_area(
            "Edit if needed before passing to next stages",
            value=st.session_state["transcribed_text"],
            height=160,
            key="transcribed_edit",
        )
        if edited_text != st.session_state["transcribed_text"]:
            if st.button("💾 Save edits"):
                st.session_state["transcribed_text"] = edited_text
                st.rerun()

        st.download_button(
            "📥 Download Transcript",
            data=st.session_state["transcribed_text"],
            file_name="transcript_saaras.txt",
            mime="text/plain",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# STAGE 1 — Formal Translation (Sarvam-Translate)
# ══════════════════════════════════════════════════════════════
st.subheader("🔷 Stage 1 — Formal Translation")
st.markdown(
    "<span class='model-badge-sarvam'>Sarvam-Translate v1 · Formal</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Translates the English transcript into the citizen's language "
    "in formal register — accurate, preserves all details."
)

btn_stage1 = st.button(
    "🔷 Translate to Citizen Language (Sarvam · Formal)",
    type="primary",
    use_container_width=True,
    disabled=not api_key or not st.session_state["transcribed_text"],
)

if st.session_state["formal_translation_out"]:
    st.success("✅ Stage 1 complete")

if btn_stage1:
    with st.spinner(f"Sarvam-Translate → {MAYURA_SUPPORTED.get(citizen_lang)}…"):
        try:
            numerals_fmt = "native" if use_native_numerals else "international"
            results = run_translation(
                st.session_state["transcribed_text"],
                [citizen_lang],
                speaker_gender,
                "formal",
                numerals_fmt,
                api_key,
            )
            if isinstance(results.get(citizen_lang), Exception):
                st.error(f"❌ {results[citizen_lang]}")
            else:
                st.session_state["formal_translation_out"] = results[citizen_lang]
                st.session_state["pipeline_log"].append({
                    "stage":   "Stage 1",
                    "model":   "Sarvam-Translate v1 · Formal",
                    "preview": results[citizen_lang][:120],
                })
                st.success("✅ Formal translation done!")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 1 failed: {e}")

if st.session_state["formal_translation_out"]:
    with st.expander("📖 Stage 1 Result — Formal Translation", expanded=True):
        st.text_area(
            "Formal",
            value=st.session_state["formal_translation_out"],
            height=160,
            key="formal_out_s1",
            label_visibility="collapsed",
        )
        st.download_button(
            "📥 Download Formal Translation",
            data=st.session_state["formal_translation_out"],
            file_name=f"formal_{citizen_lang}.txt",
            mime="text/plain",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# STAGE 2 — Colloquial Explanation (Mayura)
# ══════════════════════════════════════════════════════════════
st.subheader("🟣 Stage 2 — Colloquial Explanation")
st.markdown(
    "<span class='model-badge-mayura'>Mayura v1 · Colloquial</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Same English transcript, translated into citizen's language "
    "in plain spoken style — easy to understand, no jargon."
)

btn_stage2 = st.button(
    "🟣 Explain in Colloquial Language (Mayura)",
    type="primary",
    use_container_width=True,
    disabled=(
        not api_key
        or not st.session_state["transcribed_text"]
        or citizen_lang not in MAYURA_SUPPORTED
    ),
)

if citizen_lang not in MAYURA_SUPPORTED:
    st.warning(
        f"⚠️ Mayura does not support {LANGUAGES.get(citizen_lang)} yet. "
        "Use Stage 1 (Sarvam) instead."
    )

if st.session_state["colloquial_out"]:
    st.success("✅ Stage 2 complete")

if btn_stage2:
    with st.spinner(f"Mayura · Colloquial (en-IN → {MAYURA_SUPPORTED.get(citizen_lang)})…"):
        try:
            numerals_fmt = "native" if use_native_numerals else "international"
            result = run_mayura_chunked(
                st.session_state["transcribed_text"],  # English input
                citizen_lang,
                speaker_gender,
                "colloquial",
                numerals_fmt,
                api_key,
            )
            st.session_state["colloquial_out"] = result
            st.session_state["pipeline_log"].append({
                "stage":   "Stage 2",
                "model":   "Mayura v1 · Colloquial",
                "preview": result[:120],
            })
            st.success("✅ Colloquial explanation ready!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 2 failed: {e}")

if st.session_state["colloquial_out"]:
    with st.expander("🗣️ Stage 2 Result — Colloquial Explanation", expanded=True):
        st.text_area(
            "Colloquial",
            value=st.session_state["colloquial_out"],
            height=160,
            key="colloquial_out_s2",
            label_visibility="collapsed",
        )
        st.download_button(
            "📥 Download Colloquial Explanation",
            data=st.session_state["colloquial_out"],
            file_name=f"colloquial_{citizen_lang}.txt",
            mime="text/plain",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# STAGE 3 — Citizen Voice Reply (Saaras Transcribe mode)
# ══════════════════════════════════════════════════════════════
st.subheader("🎙️ Stage 3 — Citizen's Voice Reply (Optional)")
st.markdown(
    "<span class='model-badge-saaras'>Saaras v3 · Translate mode</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Citizen speaks their reply in their own dialect/language → "
    "Saaras transcribes → English text → used for legal draft."
)

reply_audio_bytes    = None
reply_audio_filename = "reply.wav"

reply_input_method = st.radio(
    "Citizen reply input",
    options=["📁 Upload reply audio", "🎤 Record reply", "⌨️ Type reply manually"],
    horizontal=True,
    key="reply_method",
)

if reply_input_method == "📁 Upload reply audio":
    reply_uploaded = st.file_uploader(
        "Upload citizen's reply audio",
        type=["wav", "mp3", "ogg", "flac", "aac", "m4a", "webm"],
        key="reply_upload",
    )
    if reply_uploaded:
        reply_audio_bytes    = reply_uploaded.read()
        reply_audio_filename = reply_uploaded.name
        st.audio(reply_audio_bytes)

elif reply_input_method == "🎤 Record reply":
    reply_recorded = st.audio_input(
        "Record citizen's reply",
        key="reply_record",
    )
    if reply_recorded:
        reply_audio_bytes    = reply_recorded.read()
        reply_audio_filename = "reply.wav"
        st.audio(reply_audio_bytes)

else:
    # Manual text fallback
    manual_reply = st.text_area(
        "Type citizen's reply (any language / dialect)",
        height=120,
        placeholder=(
            "e.g. meri zameen 3 bigha hai, muavza nahi mila, "
            "objection dena chahta hu…"
        ),
        key="manual_reply_text",
    )
    if manual_reply.strip():
        st.session_state["citizen_reply_english"] = manual_reply.strip()

# Transcribe reply button
btn_stage3 = st.button(
    "🟢 Transcribe Citizen Reply (Saaras v3)",
    type="primary",
    use_container_width=True,
    disabled=(
        not api_key
        or (reply_audio_bytes is None
            and not st.session_state.get("citizen_reply_english", ""))
    ),
    key="btn_stage3",
)

if st.session_state.get("citizen_reply_english"):
    st.success("✅ Stage 3 complete")

if btn_stage3:
    if reply_audio_bytes:
        with st.spinner("Saaras v3 — transcribing citizen reply…"):
            try:
                reply_transcript, _ = transcribe_audio(
                    reply_audio_bytes,
                    reply_audio_filename,
                    "unknown",       # auto-detect citizen's language
                    "translate",     # → English for drafting
                    api_key,
                )
                st.session_state["citizen_reply_english"] = reply_transcript
                st.session_state["pipeline_log"].append({
                    "stage":   "Stage 3",
                    "model":   "Saaras v3 · Translate",
                    "preview": reply_transcript[:120],
                })
                st.success("✅ Reply transcribed to English!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Stage 3 transcription failed: {e}")
    elif st.session_state.get("citizen_reply_english"):
        st.info("ℹ️ Using manually entered reply text.")

if st.session_state.get("citizen_reply_english"):
    with st.expander("✅ Stage 3 Result — Citizen Reply (English)", expanded=True):
        st.text_area(
            "Reply",
            value=st.session_state["citizen_reply_english"],
            height=130,
            key="reply_out_s3",
            label_visibility="collapsed",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# STAGE 4 — Formal Legal Draft (Template)
# ══════════════════════════════════════════════════════════════
st.subheader("📜 Stage 4 — Formal Legal Draft")
st.markdown(
    "<span class='model-badge-sarvam'>English Letter Template</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Assembles a formal English legal letter from the citizen's reply — "
    "ready to print and submit. No translation needed."
)

btn_stage4 = st.button(
    "🔷 Generate Legal Draft",
    type="primary",
    use_container_width=True,
    disabled=not st.session_state.get("citizen_reply_english"),
)

if st.session_state["legal_draft_out"]:
    st.success("✅ Stage 4 complete — Legal draft ready!")

if btn_stage4 and st.session_state.get("citizen_reply_english"):
    with st.spinner("Building formal English legal letter…"):
        try:
            draft = build_legal_draft(
                citizen_situation    = st.session_state["citizen_reply_english"],
                doc_type_label       = DOC_TYPES[doc_type],
                original_doc_snippet = st.session_state.get("transcribed_text", "")[:300],
                gender               = speaker_gender,
            )
            st.session_state["legal_draft_out"] = draft
            st.session_state["pipeline_log"].append({
                "stage":   "Stage 4",
                "model":   "Template · English",
                "preview": draft[:120],
            })
            st.success("✅ Legal draft ready!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 4 failed: {e}")

if st.session_state["legal_draft_out"]:
    with st.expander("📜 Stage 4 Result — Formal Legal Draft", expanded=True):
        st.text_area(
            "Draft",
            value=st.session_state["legal_draft_out"],
            height=320,
            key="draft_out_s4",
            label_visibility="collapsed",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "📥 Download English Draft",
                data=st.session_state["legal_draft_out"],
                file_name=f"legal_draft_{doc_type}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col_b:
            # Combined full package
            package = "\n\n".join(filter(None, [
                "=== TRANSCRIPT (Saaras) ===\n"    + st.session_state.get("transcribed_text", ""),
                "=== FORMAL TRANSLATION ===\n"     + st.session_state.get("formal_translation_out", ""),
                "=== COLLOQUIAL EXPLANATION ===\n" + st.session_state.get("colloquial_out", ""),
                "=== LEGAL DRAFT ===\n"            + st.session_state.get("legal_draft_out", ""),
            ]))
            st.download_button(
                "📦 Download Full Package",
                data=package,
                file_name=f"kisaanvaani_full_{doc_type}.txt",
                mime="text/plain",
                use_container_width=True,
            )

st.markdown("---")

# ── Pipeline Audit Log ────────────────────────────────────────
if st.session_state["pipeline_log"]:
    with st.expander("🔍 Pipeline Audit Log", expanded=False):
        for i, entry in enumerate(st.session_state["pipeline_log"], 1):
            model = entry["model"]
            badge = (
                "model-badge-saaras"  if "Saaras"  in model else
                "model-badge-mayura"  if "Mayura"  in model else
                "model-badge-sarvam"
            )
            st.markdown(
                f"**{entry['stage']}** — "
                f"<span class='{badge}'>{model}</span><br>"
                f"<small>{entry['preview']}…</small>",
                unsafe_allow_html=True,
            )
            if i < len(st.session_state["pipeline_log"]):
                st.divider()

# ── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**KisaanVaani** — किसान वाणी · Voice-First Legal Aid · "
    "Powered by Sarvam AI · "
    f"Saaras v3 · Mayura v1 · Sarvam-Translate v1 · "
    f"Pricing: ₹{COST_PER_10K} per 10,000 chars · "
    "Audio sent directly to Sarvam API · Not stored"
)