# ============================================================
# SARVAM API TRANSLATOR DASHBOARD (Optimized)
# ============================================================

import streamlit as st
import requests

# ── Constants ────────────────────────────────────────────────
API_URL = "https://api.sarvam.ai/translate"
SOURCE_LANG = "en-IN"
REQUEST_TIMEOUT = 60

LANGUAGES: dict[str, str] = {
    "hi-IN":  "हिन्दी (Hindi)",
    "bn-IN":  "বাংলা (Bengali)",
    "ta-IN":  "தமிழ் (Tamil)",
    "te-IN":  "తెలుగు (Telugu)",
    "mr-IN":  "मराठी (Marathi)",
    "gu-IN":  "ગુજરાતી (Gujarati)",
    "kn-IN":  "ಕನ್ನಡ (Kannada)",
    "ml-IN":  "മലയാളം (Malayalam)",
    "od-IN":  "ଓଡ଼ିଆ (Odia)",
    "pa-IN":  "ਪੰਜਾਬੀ (Punjabi)",
    "as-IN":  "অসমীয়া (Assamese)",
    "ur-IN":  "اُردُو (Urdu)",
    "mai-IN": "मैथिली (Maithili)",
    "sat-IN": "ᱥᱟᱱᱛᱟᱲᱤ (Santali)",
    "ks-IN":  "कॉशुर (Kashmiri)",
    "ne-IN":  "नेपाली (Nepali)",
    "sd-IN":  "سنڌي (Sindhi)",
    "kok-IN": "कोंकणी (Konkani)",
    "dgo-IN": "डोगरी (Dogri)",
    "brx-IN": "बर' (Bodo)",
    "mni-IN": "মৈতৈলোন্ (Manipuri)",
    "sa-IN":  "संस्कृतम् (Sanskrit)",
}

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Sarvam Translator – Indian Languages",
    page_icon="🌐",
    layout="wide",
)

# ── Session state defaults ───────────────────────────────────
st.session_state.setdefault("translated_text", "")
st.session_state.setdefault("last_target_lang", "")

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key: str = st.text_input(
        "Sarvam API Key",
        type="password",
        placeholder="Paste your key here…",
    )
    st.caption("No key? Get one at [sarvam.ai](https://sarvam.ai/)")
    st.markdown("---")
    with st.expander("📋 All 22 supported languages"):
        st.markdown("\n".join(f"- **{c}** — {n}" for c, n in LANGUAGES.items()))

# ── Header ───────────────────────────────────────────────────
st.title("🌐 Sarvam Translator")
st.markdown("Translate English text into **22 Indian languages** via Sarvam AI.")

# ── Main layout ──────────────────────────────────────────────
col_in, col_out = st.columns(2, gap="large")

with col_in:
    st.subheader("📝 English Input")
    input_text: str = st.text_area(
        "Text to translate",
        height=300,
        placeholder="Type or paste English text here…",
        label_visibility="collapsed",
    )

    target_code: str = st.selectbox(
        "Target language",
        options=list(LANGUAGES.keys()),
        format_func=lambda c: LANGUAGES[c],
    )

    speaker_gender: str = st.radio(
        "Speaker gender (affects phrasing in gendered languages)",
        options=["Male", "Female"],
        horizontal=True,
    )


    do_translate: bool = st.button(
        "🚀 Translate",
        type="primary",
        use_container_width=True,
        disabled=not api_key,
    )
    if not api_key:
        st.caption("⬅️ Add your API key in the sidebar to enable translation.")

# ── Translation logic ────────────────────────────────────────
def call_sarvam(text: str, target: str, key: str) -> str:
    """Call Sarvam translate endpoint; return translated string or raise."""
    resp = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",},
        json={
            "input": text,
            "source_language_code": SOURCE_LANG,
            "target_language_code": target,
            "speaker_gender": speaker_gender,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()          # raises HTTPError for 4xx/5xx
    data = resp.json()
    # Sarvam API may use different keys across versions
    translated = (
        data.get("translated_text")
        or data.get("result")
        or data.get("output")
        or data.get("translation")
    )
    if not translated:
        raise ValueError(f"Unexpected API response shape: {list(data.keys())}")
    return translated

if do_translate:
    text_clean = input_text.strip()
    if not text_clean:
        st.warning("⚠️ Please enter some text before translating.")
    else:
        with st.spinner(f"Translating to {LANGUAGES[target_code]}…"):
            try:
                result = call_sarvam(text_clean, target_code, api_key)
                st.session_state["translated_text"] = result
                st.session_state["last_target_lang"] = target_code
            except requests.exceptions.Timeout:
                st.error("❌ Request timed out. Try again or shorten the text.")
            except requests.exceptions.ConnectionError:
                st.error("❌ Could not reach Sarvam API. Check your connection.")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                detail = ""
                try:
                    detail = e.response.json().get("message", e.response.text[:200])
                except Exception:
                    pass
                st.error(f"❌ API error {status}: {detail or str(e)}")
            except ValueError as e:
                st.error(f"❌ {e}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")

# ── Output column ────────────────────────────────────────────
with col_out:
    st.subheader("📖 Translation")
    translated = st.session_state["translated_text"]
    if translated:
        lang_name = LANGUAGES.get(st.session_state["last_target_lang"], "")
        st.success(f"✅ {lang_name}")
        st.text_area(
            "Result",
            value=translated,
            height=300,
            label_visibility="collapsed",
        )
        st.download_button(
            "📥 Download",
            data=translated,
            file_name=f"translation_{st.session_state['last_target_lang']}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    else:
        st.info("Translation will appear here.")

# ── Footer ───────────────────────────────────────────────────
st.markdown("---")
st.caption("Powered by Sarvam AI · text sent directly to Sarvam — not stored by this app.")