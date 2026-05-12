# ============================================================
# NYAYASETU — Mayura Colloquial Translation Dashboard v1
# Companion to: sarvam_translate_op.py
#
# Pipeline:
#   1. Formal/legal INPUT  → Sarvam-Translate (formal mode)
#                            → Accurate structured translation
#   2. Translated output   → Mayura (colloquial mode)
#                            → Plain-language explanation
#   3. User's dialect reply→ Mayura (code-mixed input)
#                            → Understood + cleaned
#   4. Cleaned reply       → Sarvam-Translate (formal mode)
#                            → Final formal letter/draft
# ============================================================

import hashlib
import concurrent.futures
import streamlit as st
import requests

# ── Import shared utilities from Sarvam Translate ────────────
# We reuse: _call_sarvam_once, translate_cached, run_translation
# and all constants (LANGUAGES, MODES, BETA_LANGS, etc.)
from SARVAM_TRANSLATE_OP import (
    _call_sarvam_once,
    translate_cached,
    run_translation,
    LANGUAGES,
    MODES,
    BETA_LANGS,
    SOURCE_LANG,
    MAX_WORKERS,
    COST_PER_10K,
)

# ── Mayura-specific Constants ─────────────────────────────────
MAYURA_API_URL      = "https://api.sarvam.ai/translate"   # same endpoint, different mode
MAYURA_MODEL        = "mayura:v1"
REQUEST_TIMEOUT     = 60

# Mayura supports 11 languages — subset of Sarvam's 22
MAYURA_SUPPORTED: dict[str, str] = {
    k: v for k, v in LANGUAGES.items() if k in {
        "hi-IN", "bn-IN", "ta-IN", "te-IN",
        "mr-IN", "gu-IN", "kn-IN", "ml-IN",
        "od-IN", "pa-IN", "ur-IN",
    }
}

MAYURA_MODES = {
    "colloquial":  ("🗣️ Colloquial",  "Plain spoken language, easy to understand"),
    "code-mixed":  ("💬 Code-Mixed",  "Mix of English + regional language, casual tone"),
    "formal":      ("🏛️ Formal",      "Formal register — reuse Sarvam for this"),
}

# Document types for the NyayaSetu legal aid pipeline
DOC_TYPES = {
    "court_notice":    "⚖️ Court Notice",
    "land_deed":       "🏡 Land Deed / Mutation",
    "fir":             "🚨 FIR / Police Report",
    "rti":             "📋 RTI Application",
    "govt_order":      "📜 Government Order",
    "loan_agreement":  "💰 Loan / Finance Agreement",
    "other":           "📄 Other Document",
}

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="NyayaSetu — Legal Aid in Your Language",
    page_icon="⚖️",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    .pipeline-step {
        background: #1e293b;
        border-left: 4px solid #f59e0b;
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.88rem;
        color: #e2e8f0;
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
    .step-arrow {
        text-align: center;
        color: #f59e0b;
        font-size: 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────
st.session_state.setdefault("stage", "input")           # input | explained | replied | drafted
st.session_state.setdefault("formal_translation", "")
st.session_state.setdefault("colloquial_explanation", "")
st.session_state.setdefault("citizen_reply_raw", "")
st.session_state.setdefault("formal_draft", "")
st.session_state.setdefault("pipeline_log", [])

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    api_key: str = st.text_input(
        "Sarvam / Mayura API Key",
        type="password",
        placeholder="Paste your key here…",
    )
    st.caption("Both Sarvam-Translate and Mayura use the same key.")
    st.caption("No key? Get one at [sarvam.ai](https://sarvam.ai/)")

    st.markdown("---")
    st.subheader("👤 Citizen Profile")

    citizen_lang = st.selectbox(
        "Citizen's language",
        options=list(MAYURA_SUPPORTED.keys()),
        format_func=lambda c: MAYURA_SUPPORTED[c],
        index=0,
        help="Language the citizen reads and speaks.",
    )

    speaker_gender = st.radio(
        "Speaker gender",
        options=["Male", "Female"],
        horizontal=True,
        help="Affects verb/pronoun forms in gendered languages.",
    )

    use_native_numerals = st.toggle(
        "Native numerals",
        value=False,
        help="Show ४२ instead of 42 in Hindi, etc.",
    )

    st.markdown("---")
    st.subheader("📄 Document Type")
    doc_type = st.selectbox(
        "What kind of document?",
        options=list(DOC_TYPES.keys()),
        format_func=lambda k: DOC_TYPES[k],
    )

    st.markdown("---")
    st.subheader("🔬 Model Info")
    st.markdown("""
    <span class='model-badge-sarvam'>Sarvam-Translate v1</span>
    Used for:
    - Formal document translation
    - Final legal draft output
    - 22 language support

    <br><br>
    <span class='model-badge-mayura'>Mayura v1</span>
    Used for:
    - Colloquial plain-language explanation
    - Code-mixed citizen input parsing
    - 11 language support
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 Reset Full Pipeline", use_container_width=True):
        for key in ["stage", "formal_translation", "colloquial_explanation",
                    "citizen_reply_raw", "formal_draft", "pipeline_log"]:
            st.session_state[key] = "" if key != "stage" else "input"
            if key == "pipeline_log":
                st.session_state[key] = []
        st.rerun()

# ── Mayura-specific API call ──────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def mayura_translate_cached(
    text: str,
    target: str,
    gender: str,
    mode: str,          # "colloquial" or "code-mixed"
    numerals: str,
    key_hash: str,
    _key: str,
) -> str:
    """
    Calls Mayura model for colloquial / code-mixed translation.
    Same caching strategy as sarvam translate_cached.
    Reuses _call_sarvam_once with mayura model string injected
    via a thin wrapper since the endpoint and payload are identical.
    """
    # Mayura mode values per official docs:
    # "formal" | "modern-colloquial" | "classic-colloquial" | "code-mixed"
    mode_map = {
        "colloquial":  "modern-colloquial",
        "code-mixed":  "code-mixed",
        "formal":      "formal",
    }
    api_mode = mode_map.get(mode, "modern-colloquial")

    payload = {
        "input":                text,
        "source_language_code": "auto",
        "target_language_code": target,
        "speaker_gender":       gender,
        "mode":                 api_mode,
        "model":                MAYURA_MODEL,
        "numerals_format":      numerals,
    }

    resp = requests.post(
        MAYURA_API_URL,
        headers={
            "Content-Type":         "application/json",
            "api-subscription-key": _key,
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    # Expose the actual API error body instead of a generic 400
    if not resp.ok:
        try:
            err_detail = resp.json()
        except Exception:
            err_detail = resp.text[:300]
        raise requests.exceptions.HTTPError(
            f"HTTP {resp.status_code} — Mayura API error: {err_detail}",
            response=resp,
        )

    data = resp.json()
    translated = (
        data.get("translated_text")
        or data.get("result")
        or data.get("output")
        or data.get("translation")
    )
    if not translated:
        raise ValueError(
            f"Unexpected Mayura API response keys: {list(data.keys())} | full: {data}"
        )
    return translated


def run_mayura(text: str, target: str, gender: str, mode: str,
               numerals: str, key: str) -> str:
    key_hash = hashlib.md5(key.encode()).hexdigest()
    return mayura_translate_cached(text, target, gender, mode, numerals, key_hash, key)


# ── Pipeline step runner ──────────────────────────────────────
def log_step(step: str, model: str, result_preview: str):
    st.session_state["pipeline_log"].append({
        "step":    step,
        "model":   model,
        "preview": result_preview[:120] + ("…" if len(result_preview) > 120 else ""),
    })


# ── Header ────────────────────────────────────────────────────
st.title("⚖️ NyayaSetu — न्यायसेतु")
st.markdown(
    "**Legal Aid in Your Language** · "
    "Powered by <span class='model-badge-sarvam'>Sarvam-Translate</span> + "
    "<span class='model-badge-mayura'>Mayura</span>",
    unsafe_allow_html=True,
)
st.caption(
    "Upload or paste a legal document → Understand it in plain language → "
    "Reply in your dialect → Get a formal legal letter."
)
st.markdown("---")

# ── Pipeline visual ───────────────────────────────────────────
with st.expander("📊 How the pipeline works", expanded=False):
    st.markdown("""
    <div class='pipeline-step'>
        <b>Step 1</b> &nbsp;
        <span class='model-badge-sarvam'>Sarvam-Translate · Formal</span><br>
        Legal document (English/Hindi) → Accurate translation in citizen's language
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Step 2</b> &nbsp;
        <span class='model-badge-mayura'>Mayura · Colloquial</span><br>
        Translated text → Plain-language explanation (spoken style, no jargon)
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Step 3</b> &nbsp;
        <span class='model-badge-mayura'>Mayura · Code-Mixed Input</span><br>
        Citizen's dialect / broken-language reply → Understood and cleaned
    </div>
    <div class='step-arrow'>↓</div>
    <div class='pipeline-step'>
        <b>Step 4</b> &nbsp;
        <span class='model-badge-sarvam'>Sarvam-Translate · Formal</span><br>
        Cleaned reply → Formal legal objection / RTI / response letter
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STAGE 1 — Document Input & Formal Translation (Sarvam)
# ═══════════════════════════════════════════════════════════════
st.subheader("📄 Stage 1 — Upload Legal Document")
st.caption(
    f"Document type: **{DOC_TYPES[doc_type]}** · "
    f"Citizen language: **{MAYURA_SUPPORTED.get(citizen_lang, citizen_lang)}**"
)

input_doc: str = st.text_area(
    "Paste the legal document text here (English or formal Hindi)",
    height=200,
    placeholder=(
        "e.g. NOTICE UNDER SECTION 4 OF THE LAND ACQUISITION ACT...\n\n"
        "You are hereby informed that the Government of Uttar Pradesh intends "
        "to acquire 3 bigha of agricultural land..."
    ),
    label_visibility="visible",
    key="input_doc_area",
)

char_count = len(input_doc)
cost_est   = (char_count / 10_000) * COST_PER_10K
c1, c2, c3 = st.columns(3)
c1.metric("Characters", f"{char_count:,}")
c2.metric("Est. cost (both models)", f"₹{cost_est * 2:.4f}")
c3.metric("Pipeline stage", st.session_state["stage"].upper())

col1, col2 = st.columns(2)
with col1:
    btn_stage1 = st.button(
        "🔷 Step 1 — Translate Document (Sarvam-Formal)",
        type="primary",
        use_container_width=True,
        disabled=not api_key or not input_doc.strip(),
    )
with col2:
    if st.session_state["formal_translation"]:
        st.success("✅ Stage 1 complete")

if btn_stage1:
    with st.spinner(f"Sarvam-Translate → {MAYURA_SUPPORTED[citizen_lang]}…"):
        try:
            numerals_fmt = "native" if use_native_numerals else "international"
            result = run_translation(
                input_doc.strip(),
                [citizen_lang],
                speaker_gender,
                "formal",           # always formal for legal documents
                numerals_fmt,
                api_key,
            )
            if isinstance(result.get(citizen_lang), Exception):
                st.error(f"❌ Sarvam error: {result[citizen_lang]}")
            else:
                st.session_state["formal_translation"] = result[citizen_lang]
                st.session_state["stage"] = "explained"
                log_step("Formal Translation", "Sarvam-Translate v1",
                         result[citizen_lang])
                st.success("✅ Document translated successfully!")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 1 failed: {e}")

# Show Stage 1 result
if st.session_state["formal_translation"]:
    with st.expander("📖 Stage 1 Result — Formal Translation", expanded=True):
        st.markdown(
            f"<span class='model-badge-sarvam'>Sarvam-Translate v1 · Formal</span>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "Formal translation",
            value=st.session_state["formal_translation"],
            height=180,
            key="formal_out",
            label_visibility="collapsed",
        )
        st.download_button(
            "📥 Download Formal Translation",
            data=st.session_state["formal_translation"],
            file_name=f"formal_{citizen_lang}_{doc_type}.txt",
            mime="text/plain",
        )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STAGE 2 — Plain-Language Explanation (Mayura Colloquial)
# ═══════════════════════════════════════════════════════════════
st.subheader("🗣️ Stage 2 — Explain in Plain Language (Mayura)")
st.caption("Mayura converts the formal translation into colloquial spoken language.")

# ── Mayura rules (from official docs) ────────────────────────
# 1. Max 900 chars per request (hard limit is 1000 — we stay safe)
# 2. Must translate BETWEEN languages (en-IN → target), NOT same→same
# 3. Source MUST be English (en-IN) or use "auto"
# So: we take the ORIGINAL English input_doc, chunk it to 900 chars,
# translate each chunk en-IN → citizen_lang in colloquial mode,
# then rejoin. This is the correct Mayura usage pattern.

MAYURA_CHUNK_SIZE = 900

def _chunk_text(text: str, size: int) -> list[str]:
    """Split text into chunks of max `size` chars, breaking on sentences."""
    chunks, current = [], ""
    for sentence in text.replace("\n", " ").split(". "):
        candidate = (current + ". " + sentence).strip() if current else sentence
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sentence
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if c]

def run_mayura_chunked(text: str, target: str, gender: str,
                       mode: str, numerals: str, key: str) -> str:
    """
    Chunks English text to 900-char pieces, translates each via Mayura
    in colloquial mode (en-IN → target), then rejoins.
    """
    chunks = _chunk_text(text, MAYURA_CHUNK_SIZE)
    if not chunks:
        return ""

    key_hash = hashlib.md5(key.encode()).hexdigest()

    def _one(chunk):
        return mayura_translate_cached(
            chunk, target, gender, mode, numerals, key_hash, key
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_one, c) for c in chunks]
        parts   = [f.result() for f in futures]

    return " ".join(parts)

btn_stage2 = st.button(
    "🟣 Step 2 — Translate in Colloquial Language (Mayura)",
    type="primary",
    use_container_width=True,
    disabled=(
        not api_key
        or not input_doc.strip()
        or citizen_lang not in MAYURA_SUPPORTED
    ),
)

if citizen_lang not in MAYURA_SUPPORTED:
    st.warning(
        f"⚠️ Mayura does not support **{LANGUAGES.get(citizen_lang)}** yet. "
        "Stage 1 (Sarvam) translation is still available."
    )

# Warn if English input is missing
if not input_doc.strip() and api_key:
    st.caption("⬆️ Paste the English document in Stage 1 first.")

if st.session_state["colloquial_explanation"]:
    st.success("✅ Stage 2 complete")

if btn_stage2 and input_doc.strip():
    with st.spinner(f"Mayura · Colloquial (en-IN → {MAYURA_SUPPORTED[citizen_lang]})…"):
        try:
            numerals_fmt = "native" if use_native_numerals else "international"
            # Correct usage: English source → Indian language target, colloquial mode
            result = run_mayura_chunked(
                input_doc.strip(),   # ← original English, NOT the Hindi translation
                citizen_lang,        # ← en-IN → hi-IN (cross-language, valid)
                speaker_gender,
                "colloquial",
                numerals_fmt,
                api_key,
            )
            st.session_state["colloquial_explanation"] = result
            st.session_state["stage"] = "replied"
            log_step("Colloquial Translation", "Mayura v1", result)
            st.success("✅ Colloquial translation ready!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 2 failed: {e}")

if st.session_state["colloquial_explanation"]:
    with st.expander("🗣️ Stage 2 Result — Plain Language Explanation", expanded=True):
        st.markdown(
            "<span class='model-badge-mayura'>Mayura v1 · Colloquial</span>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "Plain explanation",
            value=st.session_state["colloquial_explanation"],
            height=180,
            key="colloquial_out",
            label_visibility="collapsed",
        )
        st.download_button(
            "📥 Download Plain Explanation",
            data=st.session_state["colloquial_explanation"],
            file_name=f"explanation_{citizen_lang}_{doc_type}.txt",
            mime="text/plain",
        )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STAGE 3 — Citizen's Reply (Mayura Code-Mixed Input)
# ═══════════════════════════════════════════════════════════════
st.subheader("✍️ Stage 3 — Citizen's Reply (in their own words)")
st.caption(
    "The citizen types their situation in dialect, broken language, or code-mixed text. "
    "Mayura parses it."
)

citizen_reply: str = st.text_area(
    "Citizen's reply (any dialect, code-mixed, broken grammar — type naturally)",
    height=140,
    placeholder=(
        "e.g. meri zameen 3 bigha hai, papa ke naam pe thi, unka 2020 mein intaqaal hua. "
        "mujhe koi muavza nahi mila. mai objection dena chahti hu. "
        "kya karna padega aur kitne din hain?"
    ),
    key="citizen_reply_area",
)

btn_stage3 = st.button(
    "🟣 Step 3 — Parse Citizen's Reply (Mayura Code-Mixed)",
    type="primary",
    use_container_width=True,
    disabled=not api_key or not citizen_reply.strip(),
)

if st.session_state["citizen_reply_raw"]:
    st.success("✅ Stage 3 complete")

if btn_stage3:
    with st.spinner("Mayura · Code-Mixed — parsing citizen's reply…"):
        try:
            numerals_fmt = "native" if use_native_numerals else "international"
            # We translate the citizen's code-mixed reply back to English
            # by treating their reply as the input and targeting en-IN
            # Note: we temporarily swap source/target logic here
            resp = requests.post(
                MAYURA_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "api-subscription-key": api_key,
                },
                json={
                    "input":                citizen_reply.strip(),
                    "source_language_code": citizen_lang,    # citizen's language as source
                    "target_language_code": SOURCE_LANG,     # en-IN as target for drafting
                    "speaker_gender":       speaker_gender,
                    "mode":                 "code-mixed",
                    "model":                MAYURA_MODEL,
                    "numerals_format":      numerals_fmt,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            parsed = (
                data.get("translated_text")
                or data.get("result")
                or data.get("output")
                or data.get("translation")
            )
            if not parsed:
                raise ValueError(f"Unexpected response: {list(data.keys())}")
            st.session_state["citizen_reply_raw"] = parsed
            log_step("Code-Mixed Parse", "Mayura v1", parsed)
            st.success("✅ Citizen's reply understood!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 3 failed: {e}")

if st.session_state["citizen_reply_raw"]:
    with st.expander("✅ Stage 3 Result — Parsed Reply (English)", expanded=True):
        st.markdown(
            "<span class='model-badge-mayura'>Mayura v1 · Code-Mixed → English</span>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "Parsed reply",
            value=st.session_state["citizen_reply_raw"],
            height=140,
            key="parsed_reply_out",
            label_visibility="collapsed",
        )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STAGE 4 — Formal Legal Draft (Sarvam-Translate Formal)
# ═══════════════════════════════════════════════════════════════
st.subheader("📜 Stage 4 — Generate Formal Legal Draft (Sarvam)")
st.caption(
    "Sarvam-Translate converts the citizen's parsed reply into a formal "
    "legal letter / objection / RTI in English — ready to submit."
)

# ── Stage 4 generates English letter directly from template ──
# We do NOT call run_translation() here.
# Reason: Sarvam-Translate translates FROM English INTO Indian languages.
# The citizen's reply (Stage 3) is already in English.
# Sending it back through translate() would corrupt it to Hindi/other.
# Instead: build the formal English letter from a structured template.

def build_legal_draft(
    citizen_situation: str,
    doc_type_label: str,
    original_doc_snippet: str,
    gender: str,
) -> str:
    """
    Builds a ready-to-submit formal English legal letter
    from the citizen's parsed English situation (Stage 3 output).
    No API call needed — pure template assembly.
    """
    from datetime import date
    salutation = "Sir/Madam"
    pronoun    = "He" if gender == "Male" else "She"
    today      = date.today().strftime("%d %B %Y")

    return f"""Date: {today}

To,
The Competent Authority / Land Acquisition Collector,
[District], [State].

Subject: Formal Objection / Response to {doc_type_label}

Respected {salutation},

I, the undersigned, hereby submit this formal response with reference to the
{doc_type_label} issued to me. The details of my situation are as follows:

{citizen_situation}

In light of the above facts, I respectfully:

1. Object to the proceedings / decision as described above.
2. Request that my case be reviewed in accordance with applicable law.
3. Request that no further action be taken until this objection is duly considered.
4. Request written acknowledgement of this letter within 30 days of receipt.

I further state that I have not received any prior communication, compensation,
or notice as required under the applicable provisions of law.

Reference — Original document excerpt:
"{original_doc_snippet}"

I request that this matter be treated with urgency and that my rights as a
citizen be duly protected.

Yours faithfully,

_______________________
[Citizen's Full Name]
[Village / Address]
[District, State]
[Date: {today}]

Enclosures:
1. Copy of the original notice / document
2. Any supporting documents (land records, ID proof, etc.)
"""

btn_stage4 = st.button(
    "🔷 Step 4 — Generate Formal Legal Draft (English Letter)",
    type="primary",
    use_container_width=True,
    disabled=not st.session_state["citizen_reply_raw"],
)

if st.session_state["formal_draft"]:
    st.success("✅ Stage 4 complete — Legal draft ready!")

if btn_stage4 and st.session_state["citizen_reply_raw"]:
    with st.spinner("Building formal English legal letter…"):
        try:
            draft = build_legal_draft(
                citizen_situation    = st.session_state["citizen_reply_raw"],
                doc_type_label       = DOC_TYPES[doc_type],
                original_doc_snippet = input_doc[:300] if input_doc else "Not provided",
                gender               = speaker_gender,
            )
            st.session_state["formal_draft"] = draft
            log_step("Formal Legal Draft", "Template (English)", draft)
            st.success("✅ Formal legal draft generated!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Stage 4 failed: {e}")

if st.session_state["formal_draft"]:
    with st.expander("📜 Stage 4 Result — Formal Legal Draft", expanded=True):
        st.markdown(
            "<span class='model-badge-sarvam'>Sarvam-Translate v1 · Formal</span>",
            unsafe_allow_html=True,
        )

        # Multi-language tabs if both were generated
        draft_results = {}
        if st.session_state["formal_draft"]:
            draft_results["en-IN"] = st.session_state["formal_draft"]

        tabs = st.tabs(
            [LANGUAGES.get(c, c) for c in draft_results]
            if len(draft_results) > 1
            else ["English Draft"]
        )
        for tab, (lang_code, draft_text) in zip(tabs, draft_results.items()):
            with tab:
                st.text_area(
                    "Draft",
                    value=draft_text,
                    height=280,
                    key=f"draft_{lang_code}",
                    label_visibility="collapsed",
                )
                st.download_button(
                    f"📥 Download Draft ({LANGUAGES.get(lang_code, 'English')})",
                    data=draft_text,
                    file_name=f"legal_draft_{doc_type}_{lang_code}.txt",
                    mime="text/plain",
                    key=f"dl_draft_{lang_code}",
                    use_container_width=True,
                )

        # Combined download
        all_content = "\n\n".join(
            f"=== {LANGUAGES.get(c, c)} ===\n{t}"
            for c, t in draft_results.items()
        )
        st.download_button(
            "📦 Download Complete Legal Package (.txt)",
            data=all_content,
            file_name=f"nyayasetu_complete_{doc_type}.txt",
            mime="text/plain",
            use_container_width=True,
        )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# PIPELINE AUDIT LOG
# ═══════════════════════════════════════════════════════════════
if st.session_state["pipeline_log"]:
    with st.expander("🔍 Pipeline Audit Log", expanded=False):
        for i, entry in enumerate(st.session_state["pipeline_log"], 1):
            badge_class = (
                "model-badge-sarvam"
                if "Sarvam" in entry["model"]
                else "model-badge-mayura"
            )
            st.markdown(
                f"**Step {i}** — {entry['step']} &nbsp;"
                f"<span class='{badge_class}'>{entry['model']}</span><br>"
                f"<small>{entry['preview']}</small>",
                unsafe_allow_html=True,
            )
            if i < len(st.session_state["pipeline_log"]):
                st.divider()

# ── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**NyayaSetu** — न्यायसेतु · Legal Aid Bridge · "
    "Powered by Sarvam AI · "
    "Data sent directly to Sarvam API · Not stored · "
    f"Pricing: ₹{COST_PER_10K} per 10,000 characters · "
    "Both models billed per character"
)