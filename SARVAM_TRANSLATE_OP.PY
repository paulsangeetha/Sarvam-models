# ============================================================
# SARVAM API TRANSLATOR DASHBOARD — Full Featured v3
# Features: parallel chunking, caching, multi-language,
#           mode selector, native numerals, cost estimator
# ============================================================

import hashlib
import concurrent.futures
import streamlit as st
import requests

# ── Constants ────────────────────────────────────────────────
API_URL          = "https://api.sarvam.ai/translate"
SOURCE_LANG      = "en-IN"
REQUEST_TIMEOUT  = 60
MAX_WORKERS      = 4       # parallel chunk / language requests
CHUNK_WARN_CHARS = 1000    # warn user text will be chunked
COST_PER_10K     = 20      # ₹ per 10,000 characters

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

# Languages with known lower quality — show a gentle warning
BETA_LANGS = {"brx-IN", "dgo-IN", "ks-IN", "mni-IN", "sat-IN", "sa-IN", "sd-IN"}

MODES = {
    "formal":     ("🏛️ Formal",     "Legal, official, government docs"),
    "modern":     ("💼 Modern",     "Business emails, general use"),
    "code-mixed": ("💬 Code-Mixed", "Casual, social media, chatbots"),
}

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Sarvam Translator – Indian Languages",
    page_icon="🌐",
    layout="wide",
)

# ── Session state defaults ───────────────────────────────────
st.session_state.setdefault("results", {})
st.session_state.setdefault("last_input", "")
st.session_state.setdefault("translation_meta", {})

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
    st.subheader("🎛️ Translation Settings")

    speaker_gender = st.radio(
        "Speaker gender",
        options=["Male", "Female"],
        horizontal=True,
        help="Affects verb forms and phrasing in gendered languages like Hindi.",
    )

    mode_key = st.radio(
        "Translation style",
        options=list(MODES.keys()),
        format_func=lambda k: MODES[k][0],
        help="\n".join(f"**{v[0]}** — {v[1]}" for v in MODES.values()),
    )
    st.caption(f"_{MODES[mode_key][1]}_")

    use_native_numerals = st.toggle(
        "Native numerals",
        value=False,
        help="Show ४२ instead of 42 in Hindi, ৪২ in Bengali, etc.",
    )

    st.markdown("---")
    with st.expander("📋 All 22 supported languages"):
        for code, name in LANGUAGES.items():
            badge = " ⚠️" if code in BETA_LANGS else ""
            st.markdown(f"- **{code}** — {name}{badge}")
        st.caption("⚠️ = quality may vary for this language")

# ── Core API call (single chunk) ─────────────────────────────
def _call_sarvam_once(text: str, target: str, gender: str, mode: str,
                      numerals: str, key: str) -> str:
    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "api-subscription-key": key,
        },
        json={
            "input": text,
            "source_language_code": SOURCE_LANG,
            "target_language_code": target,
            "speaker_gender": gender,
            "mode": mode,
            "model": "sarvam-translate:v1",
            "numerals_format": numerals,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    translated = (
        data.get("translated_text")
        or data.get("result")
        or data.get("output")
        or data.get("translation")
    )
    if not translated:
        raise ValueError(f"Unexpected API response shape: {list(data.keys())}")
    return translated


# ── Cached + chunked translation ─────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def translate_cached(text: str, target: str, gender: str, mode: str,
                     numerals: str, key_hash: str, _key: str) -> str:
    """
    Splits text on blank lines into paragraphs, translates each in
    parallel, then re-joins. Result cached 1 hour by content hash.
    _key is prefixed with _ so Streamlit doesn't hash it (it's a secret).
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if len(paragraphs) <= 1:
        return _call_sarvam_once(text, target, gender, mode, numerals, _key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(_call_sarvam_once, p, target, gender, mode, numerals, _key)
            for p in paragraphs
        ]
        translated_parts = [f.result() for f in futures]

    return "\n\n".join(translated_parts)


def run_translation(text: str, targets: list[str], gender: str, mode: str,
                    numerals: str, key: str) -> dict:
    """Translate to multiple target languages simultaneously."""
    key_hash = hashlib.md5(key.encode()).hexdigest()

    def _one(target):
        return target, translate_cached(text, target, gender, mode, numerals, key_hash, key)

    results: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_one, t): t for t in targets}
        for future in concurrent.futures.as_completed(futures):
            try:
                lang, text_out = future.result()
                results[lang] = text_out
            except Exception as e:
                results[futures[future]] = e

    return results


# ── Header ───────────────────────────────────────────────────
st.title("🌐 Sarvam Translator")
st.markdown(
    f"Translate English into **22 Indian languages** · "
    f"Style: **{MODES[mode_key][0]}** · "
    f"Gender: **{speaker_gender}** · "
    f"Numerals: **{'Native' if use_native_numerals else 'International'}**"
)

# ── Main layout ──────────────────────────────────────────────
col_in, col_out = st.columns([1, 1], gap="large")

with col_in:
    st.subheader("📝 English Input")

    input_text: str = st.text_area(
        "Text to translate",
        height=280,
        placeholder=(
            "Type or paste English text here…\n\n"
            "Separate paragraphs with a blank line.\n"
            "Long documents are split and translated in parallel."
        ),
        label_visibility="collapsed",
    )

    # ── Live stats bar ────────────────────────────────────────
    char_count  = len(input_text)
    word_count  = len(input_text.split()) if input_text.strip() else 0
    para_count  = len([p for p in input_text.split("\n\n") if p.strip()])
    cost_est    = (char_count / 10_000) * COST_PER_10K

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Characters", f"{char_count:,}")
    c2.metric("Words",      f"{word_count:,}")
    c3.metric("Paragraphs", para_count)
    c4.metric("Est. cost",  f"₹{cost_est:.3f}")

    if char_count > CHUNK_WARN_CHARS and para_count > 1:
        st.info(
            f"📄 {para_count} paragraphs detected — "
            "each will be translated in parallel for speed."
        )

    st.markdown("---")

    # ── Language selector ─────────────────────────────────────
    st.subheader("🎯 Target Languages")
    target_codes: list[str] = st.multiselect(
        "Select one or more languages (up to 6)",
        options=list(LANGUAGES.keys()),
        default=["hi-IN"],
        format_func=lambda c: LANGUAGES[c],
        max_selections=6,
        help="All selected languages are translated simultaneously.",
    )

    selected_beta = [c for c in target_codes if c in BETA_LANGS]
    if selected_beta:
        names = ", ".join(LANGUAGES[c] for c in selected_beta)
        st.warning(f"⚠️ Quality may vary for: {names}")

    st.markdown("---")

    do_translate: bool = st.button(
        "🚀 Translate Now",
        type="primary",
        use_container_width=True,
        disabled=not api_key or not target_codes,
    )
    if not api_key:
        st.caption("⬅️ Add your API key in the sidebar to enable translation.")
    elif not target_codes:
        st.caption("⬆️ Select at least one target language.")

# ── Translation execution ─────────────────────────────────────
if do_translate:
    text_clean = input_text.strip()
    if not text_clean:
        st.warning("⚠️ Please enter some text before translating.")
    else:
        numerals_fmt = "native" if use_native_numerals else "international"
        n = len(target_codes)
        spinner_label = (
            f"Translating to {n} languages in parallel…"
            if n > 1
            else f"Translating to {LANGUAGES[target_codes[0]]}…"
        )
        with st.spinner(spinner_label):
            try:
                raw = run_translation(
                    text_clean, target_codes,
                    speaker_gender, mode_key,
                    numerals_fmt, api_key,
                )
                st.session_state["results"] = raw
                st.session_state["last_input"] = text_clean
                st.session_state["translation_meta"] = {
                    "gender":   speaker_gender,
                    "mode":     mode_key,
                    "numerals": numerals_fmt,
                }
            except requests.exceptions.Timeout:
                st.error("❌ Request timed out — try shortening the text.")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot reach Sarvam API — check your connection.")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")

# ── Output column ────────────────────────────────────────────
with col_out:
    st.subheader("📖 Translations")
    results: dict = st.session_state.get("results", {})

    if not results:
        st.info("👈 Enter text, pick languages, and click **Translate Now**.")
    else:
        success = {k: v for k, v in results.items() if isinstance(v, str)}
        errors  = {k: v for k, v in results.items() if isinstance(v, Exception)}

        # ── Single language ───────────────────────────────────
        if len(success) == 1:
            lang_code, text_out = next(iter(success.items()))
            st.success(f"✅ {LANGUAGES[lang_code]}")
            st.text_area(
                "output",
                value=text_out,
                height=280,
                label_visibility="collapsed",
            )
            st.download_button(
                f"📥 Download — {LANGUAGES[lang_code]}",
                data=text_out,
                file_name=f"translation_{lang_code}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        # ── Multiple languages — tabbed ───────────────────────
        elif len(success) > 1:
            tabs = st.tabs([LANGUAGES[c] for c in success])
            for tab, (lang_code, text_out) in zip(tabs, success.items()):
                with tab:
                    st.text_area(
                        "output",
                        value=text_out,
                        height=250,
                        key=f"out_{lang_code}",
                        label_visibility="collapsed",
                    )
                    st.download_button(
                        "📥 Download",
                        data=text_out,
                        file_name=f"translation_{lang_code}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        key=f"dl_{lang_code}",
                    )

            # ── Combined download ─────────────────────────────
            combined = "\n\n".join(
                f"=== {LANGUAGES[c]} ===\n{t}" for c, t in success.items()
            )
            st.download_button(
                "📦 Download All Languages (combined .txt)",
                data=combined,
                file_name="translations_all.txt",
                mime="text/plain",
                use_container_width=True,
            )

        # ── Per-language errors ───────────────────────────────
        for lang_code, err in errors.items():
            err_str = str(err)
            try:
                if hasattr(err, "response") and err.response is not None:
                    detail = err.response.json().get("message", err.response.text[:200])
                    err_str = f"HTTP {err.response.status_code}: {detail}"
            except Exception:
                pass
            st.error(f"❌ {LANGUAGES.get(lang_code, lang_code)}: {err_str}")

        # ── Translation metadata footer ───────────────────────
        meta = st.session_state.get("translation_meta", {})
        if meta:
            st.caption(
                f"Model: `sarvam-translate:v1` · "
                f"Style: {MODES.get(meta.get('mode',''), ('?',))[0]} · "
                f"Gender: {meta.get('gender','?')} · "
                f"Numerals: {meta.get('numerals','?')}"
            )

# ── Footer ───────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Powered by **Sarvam AI** · "
    "Text sent directly to Sarvam API — not stored by this app · "
    f"Pricing: ₹{COST_PER_10K} per 10,000 characters"
)