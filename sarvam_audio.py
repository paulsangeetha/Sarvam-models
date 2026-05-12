# ============================================================
# CourtVaani — Real-Time Courtroom Interpreter
# Hackathon Demo · Powered by Sarvam AI · Saaras v3
#
# Pipeline:
#   Audio Input (court proceedings in English/Hindi)
#       ↓
#   Sarvam Smart Translate (speech → Indian language text)
#       ↓
#   Display to litigant in their mother tongue
#       ↓
#   Optional TTS readback (earpiece mode)
#
# API: POST https://api.sarvam.ai/speech-to-text
# Mode: "translate" — direct speech → translated text
# Model: saaras:v3
# ============================================================

import io
import time
import streamlit as st
import requests

# ── Import translation from existing pipeline file ────────────
from SARVAM_TRANSLATE_OP import run_translation, LANGUAGES, COST_PER_10K

# ── Constants ────────────────────────────────────────────────
SAARAS_API_URL  = "https://api.sarvam.ai/speech-to-text"
SAARAS_MODEL    = "saaras:v3"
TTS_API_URL     = "https://api.sarvam.ai/text-to-speech"
REQUEST_TIMEOUT = 60

# Target languages for the litigant (output)
TARGET_LANGUAGES: dict[str, dict] = {
    "hi-IN": {"name": "हिन्दी",     "english": "Hindi",     "flag": "🇮🇳"},
    "ta-IN": {"name": "தமிழ்",      "english": "Tamil",     "flag": "🏛️"},
    "te-IN": {"name": "తెలుగు",     "english": "Telugu",    "flag": "🌿"},
    "bn-IN": {"name": "বাংলা",       "english": "Bengali",   "flag": "🐯"},
    "mr-IN": {"name": "मराठी",      "english": "Marathi",   "flag": "🦁"},
    "gu-IN": {"name": "ગુજરાતી",    "english": "Gujarati",  "flag": "🦚"},
    "kn-IN": {"name": "ಕನ್ನಡ",      "english": "Kannada",   "flag": "🐘"},
    "ml-IN": {"name": "മലയാളം",     "english": "Malayalam", "flag": "🌴"},
    "od-IN": {"name": "ଓଡ଼ିଆ",      "english": "Odia",      "flag": "🪷"},
    "pa-IN": {"name": "ਪੰਜਾਬੀ",     "english": "Punjabi",   "flag": "🌾"},
}

# Court proceeding source languages
SOURCE_LANGUAGES: dict[str, str] = {
    "unknown": "🔍 Auto Detect",
    "en-IN":   "English (Court)",
    "hi-IN":   "Hindi (Court)",
}

# Speaker roles in a courtroom
SPEAKER_ROLES = {
    "judge":       ("⚖️", "Judge",            "#b45309"),
    "prosecutor":  ("🔴", "Prosecution",       "#991b1b"),
    "defense":     ("🔵", "Defense Counsel",   "#1e40af"),
    "witness":     ("🟡", "Witness",           "#78350f"),
    "clerk":       ("⚪", "Court Clerk",       "#374151"),
}

# ── Page Config ───────────────────────────────────────────────
st.set_page_config(
    page_title="CourtVaani — Courtroom Interpreter",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300;0,400;0,600;1,400&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+Devanagari:wght@400;600&display=swap');

/* ── Root theme ── */
:root {
    --ink:        #0f0e0d;
    --parchment:  #faf6ef;
    --gold:       #b8860b;
    --gold-light: #d4a017;
    --rust:       #8b3a2a;
    --slate:      #2c3e50;
    --muted:      #6b7280;
    --border:     #d6cfc4;
    --live-red:   #dc2626;
    --success:    #065f46;
    --card-bg:    #ffffff;
    --shadow:     0 2px 12px rgba(0,0,0,0.08);
}

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Crimson Pro', Georgia, serif !important;
    background: var(--parchment) !important;
    color: var(--ink) !important;
}

/* ── Header strip ── */
.court-header {
    background: var(--slate);
    color: #f0ebe3;
    padding: 20px 28px 16px;
    border-radius: 8px;
    margin-bottom: 24px;
    border-bottom: 3px solid var(--gold);
    position: relative;
    overflow: hidden;
}
.court-header::before {
    content: '⚖';
    position: absolute;
    right: 20px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 5rem;
    opacity: 0.08;
    pointer-events: none;
}
.court-header h1 {
    font-family: 'Crimson Pro', serif !important;
    font-size: 2rem !important;
    font-weight: 600 !important;
    margin: 0 0 4px 0 !important;
    letter-spacing: 0.01em;
    color: #f0ebe3 !important;
}
.court-header .tagline {
    font-size: 0.95rem;
    color: #b8b0a4;
    font-style: italic;
}
.live-dot {
    display: inline-block;
    width: 9px; height: 9px;
    background: var(--live-red);
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.8); }
}

/* ── Transcript bubble ── */
.transcript-bubble {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin: 10px 0;
    box-shadow: var(--shadow);
    position: relative;
}
.bubble-role {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.bubble-original {
    font-size: 0.9rem;
    color: var(--muted);
    font-style: italic;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px dashed var(--border);
}
.bubble-translated {
    font-size: 1.25rem;
    line-height: 1.6;
    font-family: 'Noto Sans Devanagari', 'Crimson Pro', serif;
    color: var(--ink);
}
.bubble-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    color: var(--muted);
    position: absolute;
    top: 12px;
    right: 16px;
}

/* ── Language badge ── */
.lang-badge {
    display: inline-block;
    background: var(--slate);
    color: #f0ebe3;
    padding: 3px 10px;
    border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    margin-left: 8px;
}
.lang-badge.active {
    background: var(--success);
}

/* ── Status bar ── */
.status-bar {
    background: var(--slate);
    color: #d1ccc5;
    padding: 8px 16px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    display: flex;
    gap: 20px;
    margin: 12px 0;
}

/* ── Article 22 callout ── */
.rights-callout {
    background: #fef3c7;
    border: 1px solid #d97706;
    border-left: 4px solid #d97706;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 0.85rem;
    color: #78350f;
    margin: 12px 0;
}

/* ── Stat cards ── */
.stat-row {
    display: flex;
    gap: 12px;
    margin: 16px 0;
}
.stat-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    flex: 1;
    text-align: center;
    box-shadow: var(--shadow);
}
.stat-card .stat-number {
    font-size: 1.8rem;
    font-weight: 600;
    color: var(--slate);
    line-height: 1;
}
.stat-card .stat-label {
    font-size: 0.75rem;
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 4px;
}

/* ── Section headers ── */
.section-head {
    font-family: 'Crimson Pro', serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--slate);
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
    margin: 20px 0 12px;
    letter-spacing: 0.02em;
}

/* ── Sidebar polish ── */
section[data-testid="stSidebar"] {
    background: var(--slate) !important;
}
section[data-testid="stSidebar"] * {
    color: #d1ccc5 !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stRadio label {
    color: #a8a29e !important;
    font-size: 0.82rem !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Streamlit overrides ── */
.stButton > button {
    font-family: 'Crimson Pro', serif !important;
    font-size: 1rem !important;
    border-radius: 6px !important;
    border: 1px solid var(--gold) !important;
    background: var(--slate) !important;
    color: #f0ebe3 !important;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: var(--gold) !important;
    color: var(--ink) !important;
}
.stButton > button[kind="primary"] {
    background: var(--rust) !important;
    border-color: var(--rust) !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover {
    background: #a04030 !important;
}

div[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    background: var(--card-bg) !important;
}

.stAlert {
    border-radius: 6px !important;
}

/* Scrollable transcript feed */
.transcript-feed {
    max-height: 520px;
    overflow-y: auto;
    padding-right: 4px;
}
.transcript-feed::-webkit-scrollbar { width: 4px; }
.transcript-feed::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
st.session_state.setdefault("transcript_log", [])       # list of dicts
st.session_state.setdefault("session_start", time.time())
st.session_state.setdefault("total_chars", 0)
st.session_state.setdefault("litigant_lang", "ta-IN")

# ── Sarvam API ────────────────────────────────────────────────
def stt_to_english(
    audio_bytes: bytes,
    filename: str,
    source_lang: str,
    api_key: str,
) -> tuple[str, str]:
    """
    Step 1: Saaras v3 in 'translate' mode.
    Speech (any Indian lang / English) → English text.
    Returns (english_text, detected_language_code).
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {
        "wav": "audio/wav", "mp3": "audio/mpeg",
        "ogg": "audio/ogg", "flac": "audio/flac",
        "aac": "audio/aac", "m4a": "audio/mp4",
        "webm": "audio/webm",
    }
    mime_type = mime_map.get(ext, "audio/wav")

    files = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
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
        raise requests.exceptions.HTTPError(
            f"HTTP {resp.status_code}: {err}", response=resp
        )

    result = resp.json()
    english_text = (
        result.get("transcript")
        or result.get("text")
        or result.get("translated_text")
        or result.get("output")
        or ""
    ).strip()
    detected_lang = result.get("language_code", source_lang or "unknown")

    if not english_text:
        raise ValueError(
            f"No transcript returned. Keys: {list(result.keys())} | Full: {result}"
        )
    return english_text, detected_lang


def smart_translate_audio(
    audio_bytes: bytes,
    filename: str,
    source_lang: str,
    target_lang: str,
    api_key: str,
) -> dict:
    """
    Two-step pipeline:
      Step 1 — Saaras v3 'translate' mode: audio → English text
      Step 2 — run_translation() from sarvam_translate_op: English → target language

    Saaras translate mode always outputs English by design.
    run_translation() handles chunking, caching, and parallel requests.
    """
    # Step 1: audio → English
    english_text, detected_lang = stt_to_english(
        audio_bytes, filename, source_lang, api_key
    )

    # Step 2: English → litigant's language via existing run_translation
    results = run_translation(
        english_text,
        [target_lang],
        "Male",
        "formal",
        "international",
        api_key,
    )

    if isinstance(results.get(target_lang), Exception):
        raise results[target_lang]

    translated_text = results[target_lang]

    return {
        "translated":    translated_text,
        "original":      english_text,
        "detected_lang": detected_lang,
    }


def text_to_speech_sarvam(text: str, lang: str, api_key: str) -> bytes | None:
    """
    Optional TTS readback using Sarvam TTS API.
    Returns audio bytes or None on failure.
    """
    try:
        resp = requests.post(
            TTS_API_URL,
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "inputs": [text[:500]],
                "target_language_code": lang,
                "speaker": "meera" if lang in ["ta-IN", "ml-IN", "kn-IN", "te-IN"] else "arvind",
                "model": "bulbul:v1",
            },
            timeout=30,
        )
        if resp.ok:
            data = resp.json()
            audios = data.get("audios", [])
            if audios:
                import base64
                return base64.b64decode(audios[0])
    except Exception:
        pass
    return None


# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚖️ CourtVaani")
    st.markdown("---")

    api_key: str = st.text_input(
        "SARVAM API KEY",
        type="password",
        placeholder="sk-…",
        help="Get your key at sarvam.ai",
    )
    st.caption("[Get API key → sarvam.ai](https://sarvam.ai/)")
    st.markdown("---")

    st.markdown("**LITIGANT LANGUAGE**")
    litigant_lang = st.selectbox(
        "Mother tongue of litigant",
        options=list(TARGET_LANGUAGES.keys()),
        format_func=lambda k: f"{TARGET_LANGUAGES[k]['flag']} {TARGET_LANGUAGES[k]['name']} ({TARGET_LANGUAGES[k]['english']})",
        index=list(TARGET_LANGUAGES.keys()).index(
            st.session_state["litigant_lang"]
        ),
        label_visibility="collapsed",
    )
    st.session_state["litigant_lang"] = litigant_lang

    st.markdown("**COURT AUDIO LANGUAGE**")
    source_lang = st.selectbox(
        "Source language",
        options=list(SOURCE_LANGUAGES.keys()),
        format_func=lambda k: SOURCE_LANGUAGES[k],
        label_visibility="collapsed",
    )

    st.markdown("**SPEAKER ROLE**")
    speaker_role = st.selectbox(
        "Who is speaking?",
        options=list(SPEAKER_ROLES.keys()),
        format_func=lambda k: f"{SPEAKER_ROLES[k][0]} {SPEAKER_ROLES[k][1]}",
        label_visibility="collapsed",
    )

    enable_tts = st.toggle(
        "🔊 Earpiece readback (TTS)",
        value=False,
        help="Reads translated text aloud in litigant's language.",
    )

    font_size = st.slider(
        "Display font size",
        min_value=14,
        max_value=32,
        value=20,
        step=2,
        help="Larger text for litigants with poor eyesight.",
    )

    st.markdown("---")
    st.markdown("**SESSION**")

    elapsed = int(time.time() - st.session_state["session_start"])
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    st.metric("Duration", f"{h:02d}:{m:02d}:{s:02d}")
    st.metric("Utterances", len(st.session_state["transcript_log"]))
    st.metric("Chars translated", st.session_state["total_chars"])

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state["transcript_log"] = []
            st.session_state["total_chars"]    = 0
            st.session_state["session_start"]  = time.time()
            st.rerun()
    with col_b:
        if st.session_state["transcript_log"]:
            export_lines = []
            for entry in st.session_state["transcript_log"]:
                role_label = SPEAKER_ROLES[entry["role"]][1]
                export_lines.append(
                    f"[{entry['timestamp']}] {role_label}\n"
                    f"  Original:   {entry['original'] or '(audio)'}\n"
                    f"  Translated: {entry['translated']}\n"
                )
            st.download_button(
                "📥 Export",
                data="\n".join(export_lines),
                file_name=f"courtvaani_session_{int(time.time())}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.72rem; color:#6b7280; line-height:1.6;'>
    <b>Model stack</b><br>
    🎙 Saaras v3 · Smart Translate<br>
    🔊 Bulbul v1 · TTS (earpiece)<br><br>
    <b>Tech</b><br>
    Single API call: speech → translated text<br>
    30s max per utterance<br>
    Auto language detection<br><br>
    <b>Privacy</b><br>
    Audio sent to Sarvam API only.<br>
    Not stored by CourtVaani.
    </div>
    """, unsafe_allow_html=True)


# ── Main layout ───────────────────────────────────────────────

# Header
lang_info = TARGET_LANGUAGES[litigant_lang]
role_info = SPEAKER_ROLES[speaker_role]

st.markdown(f"""
<div class='court-header'>
    <h1>⚖️ CourtVaani — कोर्ट वाणी</h1>
    <div class='tagline'>
        Real-Time Courtroom Interpreter · Justice in Every Language
        <span class='lang-badge active'>{lang_info['flag']} {lang_info['name']}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Constitutional callout
st.markdown("""
<div class='rights-callout'>
    <b>Article 22, Constitution of India</b> — Every person has the right to be informed
    of the grounds for any legal proceeding against them. CourtVaani ensures that right
    is meaningful — not just formal — by translating live court proceedings into the
    litigant's mother tongue in real time.
</div>
""", unsafe_allow_html=True)

# Two-column layout
col_input, col_feed = st.columns([1, 1.4], gap="large")

# ── LEFT: Audio Input ─────────────────────────────────────────
with col_input:
    st.markdown("<div class='section-head'>🎤 Court Audio Input</div>", unsafe_allow_html=True)

    input_method = st.radio(
        "Input method",
        ["📁 Upload audio", "🎤 Record live"],
        horizontal=True,
        label_visibility="collapsed",
    )

    audio_bytes   = None
    audio_filename = "court.wav"

    if input_method == "📁 Upload audio":
        uploaded = st.file_uploader(
            "Upload court audio (max 30s)",
            type=["wav", "mp3", "ogg", "flac", "aac", "m4a", "webm"],
            label_visibility="collapsed",
        )
        if uploaded:
            audio_bytes    = uploaded.read()
            audio_filename = uploaded.name
            ext = audio_filename.rsplit(".", 1)[-1]
            st.audio(audio_bytes, format=f"audio/{ext}")
            st.caption(f"`{audio_filename}` · {len(audio_bytes):,} bytes")
    else:
        recorded = st.audio_input(
            "Record court audio (max 30s)",
            label_visibility="collapsed",
        )
        if recorded:
            audio_bytes    = recorded.read()
            audio_filename = "recorded.wav"
            st.audio(audio_bytes)
            st.caption(f"Recorded · {len(audio_bytes):,} bytes")

    # Speaker role selector (compact)
    st.markdown(f"""
    <div style='margin:10px 0 6px; font-size:0.82rem; color:#6b7280; font-family:monospace;'>
        CURRENT SPEAKER:
        <span style='color:{role_info[2]}; font-weight:700;'>
            {role_info[0]} {role_info[1]}
        </span>
    </div>
    """, unsafe_allow_html=True)

    btn_translate = st.button(
        f"⚡ Translate → {lang_info['name']}",
        type="primary",
        use_container_width=True,
        disabled=(not api_key or audio_bytes is None),
    )

    if not api_key:
        st.caption("⬅️ Add your Sarvam API key in the sidebar.")
    elif audio_bytes is None:
        st.caption("⬆️ Upload or record court audio first.")

    # Process translation
    if btn_translate and audio_bytes and api_key:
        with st.spinner(f"Step 1: Saaras v3 · STT → English … then Step 2: Translate → {lang_info['english']}…"):
            try:
                t_start = time.time()
                result = smart_translate_audio(
                    audio_bytes,
                    audio_filename,
                    source_lang,
                    litigant_lang,
                    api_key,
                )
                latency_ms = int((time.time() - t_start) * 1000)

                entry = {
                    "role":        speaker_role,
                    "translated":  result["translated"],
                    "original":    result["original"],
                    "detected":    result["detected_lang"],
                    "timestamp":   time.strftime("%H:%M:%S"),
                    "latency_ms":  latency_ms,
                    "tts_audio":   None,
                }

                # TTS readback if enabled
                if enable_tts:
                    with st.spinner("Generating earpiece audio…"):
                        tts_bytes = text_to_speech_sarvam(
                            result["translated"], litigant_lang, api_key
                        )
                        entry["tts_audio"] = tts_bytes

                st.session_state["transcript_log"].insert(0, entry)
                st.session_state["total_chars"] += len(result["translated"])
                st.rerun()

            except Exception as e:
                st.error(f"❌ Translation failed: {e}")

    # Current translation highlight (most recent)
    if st.session_state["transcript_log"]:
        latest = st.session_state["transcript_log"][0]
        st.markdown("<div class='section-head'>📺 Litigant Display</div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style='
            background: #0f172a;
            border: 2px solid #b8860b;
            border-radius: 10px;
            padding: 24px;
            text-align: center;
        '>
            <div style='color:#6b7280; font-size:0.75rem; font-family:monospace;
                        text-transform:uppercase; letter-spacing:0.1em; margin-bottom:12px;'>
                {SPEAKER_ROLES[latest["role"]][0]} {SPEAKER_ROLES[latest["role"]][1]}
                &nbsp;·&nbsp; {latest["timestamp"]}
            </div>
            <div style='
                color: #f0ebe3;
                font-size: {font_size}px;
                line-height: 1.7;
                font-family: "Noto Sans Devanagari", "Crimson Pro", serif;
            '>
                {latest["translated"]}
            </div>
            <div style='margin-top:12px; color:#b8860b; font-size:0.75rem; font-family:monospace;'>
                {lang_info["flag"]} {lang_info["name"]}
                &nbsp;·&nbsp; {latest["latency_ms"]}ms
            </div>
        </div>
        """, unsafe_allow_html=True)

        if latest.get("tts_audio"):
            st.markdown("**🔊 Earpiece Audio**")
            st.audio(latest["tts_audio"], format="audio/wav", autoplay=True)


# ── RIGHT: Transcript Feed ────────────────────────────────────
with col_feed:
    st.markdown("<div class='section-head'>📜 Proceeding Transcript</div>", unsafe_allow_html=True)

    if not st.session_state["transcript_log"]:
        st.markdown("""
        <div style='
            text-align:center;
            padding:60px 20px;
            color:#9ca3af;
            font-style:italic;
            border:1px dashed #d6cfc4;
            border-radius:8px;
            background:#faf6ef;
        '>
            <div style='font-size:2.5rem; margin-bottom:12px;'>⚖️</div>
            <div style='font-size:1rem;'>
                No proceedings translated yet.<br>
                Upload or record court audio to begin.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Stats row
        total_utterances = len(st.session_state["transcript_log"])
        avg_latency = sum(
            e["latency_ms"] for e in st.session_state["transcript_log"]
        ) // total_utterances

        st.markdown(f"""
        <div class='stat-row'>
            <div class='stat-card'>
                <div class='stat-number'>{total_utterances}</div>
                <div class='stat-label'>Utterances</div>
            </div>
            <div class='stat-card'>
                <div class='stat-number'>{avg_latency}ms</div>
                <div class='stat-label'>Avg latency</div>
            </div>
            <div class='stat-card'>
                <div class='stat-number'>{st.session_state["total_chars"]}</div>
                <div class='stat-label'>Chars translated</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Feed
        # Feed - render each bubble individually to avoid raw HTML display bug
        for entry in st.session_state["transcript_log"]:
            role_icon, role_label, role_color = SPEAKER_ROLES[entry["role"]]
            original_html = (
                f"<div class='bubble-original'>{entry['original']}</div>"
                if entry["original"] else ""
            )
            st.markdown(f"""
            <div class='transcript-bubble'>
                <div class='bubble-time'>{entry['timestamp']} · {entry['latency_ms']}ms</div>
                <div class='bubble-role' style='color:{role_color};'>
                    {role_icon} {role_label}
                </div>
                {original_html}
                <div class='bubble-translated' style='font-size:{font_size - 2}px;'>
                    {entry['translated']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Quick reference — what litigant can say
    with st.expander("💡 How to use CourtVaani", expanded=False):
        st.markdown(f"""
        **For the court interpreter / NGO worker:**

        1. **Set litigant language** in the sidebar — currently **{lang_info['english']}**
        2. **Upload or record** each utterance (judge, lawyer, witness) — max 30 seconds
        3. **Select the speaker role** before translating
        4. Click **Translate** — Saaras v3 Smart Translate converts speech directly
        5. The litigant sees the translation on screen in their language
        6. Enable **Earpiece mode** for audio readback via TTS

        **Why this works:**
        Sarvam's Smart Translate performs speech-to-translated-text in a **single API call**,
        avoiding the latency of a two-step STT → MT pipeline. This makes near-real-time
        courtroom interpretation feasible on a ₹8,000 tablet.

        **Languages supported:**
        {", ".join(f'{v["flag"]} {v["english"]}' for v in TARGET_LANGUAGES.values())}
        """)

# ── Footer ────────────────────────────────────────────────────
st.markdown("---")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.caption(
        "**CourtVaani** · Real-Time Courtroom Interpreter  \n"
        "Hackathon Demo · Justice in Every Language"
    )
with col_f2:
    st.caption(
        "Powered by **Sarvam AI**  \n"
        "Saaras v3 Smart Translate · Bulbul v1 TTS"
    )
with col_f3:
    st.caption(
        "Audio processed by Sarvam API only  \n"
        "Not stored · Not logged · Private"
    )