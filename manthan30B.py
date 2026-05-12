"""
===============================================================================
PROJECT MANTHAN - Voice AI for Every Indian
===============================================================================
"""

import io
import base64
import json
import re
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

import streamlit as st
import requests

# ============================================================================
# CONFIGURATION — using plain dicts/constants (not a dataclass)
# so values are accessible as Config.LANGUAGES, Config.DOMAINS, etc.
# ============================================================================

class Config:
    SAARAS_STT_URL   = "https://api.sarvam.ai/speech-to-text"
    SARVAM_30B_URL   = "https://api.sarvam.ai/v1/chat/completions"
    MAYURA_URL       = "https://api.sarvam.ai/translate"
    BULBUL_TTS_URL   = "https://api.sarvam.ai/text-to-speech"

    SAARAS_MODEL     = "saaras:v3"
    SARVAM_30B_MODEL = "sarvam-30b"
    MAYURA_MODEL     = "mayura:v1"
    TTS_MODEL        = "bulbul:v2"

    MAX_AUDIO_SEC    = 30
    MAX_LLM_TOKENS   = 4096
    REQUEST_TIMEOUT  = 120
    TTS_CHUNK_SIZE   = 450

    LANGUAGES: Dict[str, str] = {
        "hi-IN": "हिन्दी",  "bn-IN": "বাংলা",    "ta-IN": "தமிழ்",
        "te-IN": "తెలుగు",  "mr-IN": "मराठी",     "gu-IN": "ગુજરાતી",
        "kn-IN": "ಕನ್ನಡ",   "ml-IN": "മലയാളം",   "od-IN": "ଓଡ଼ିଆ",
        "pa-IN": "ਪੰਜਾਬੀ",  "ur-IN": "اُردُو",    "en-IN": "English",
    }

    # Native script names for stronger prompting
    LANGUAGE_SCRIPTS: Dict[str, str] = {
        "hi-IN": "Devanagari (देवनागरी)",
        "bn-IN": "Bengali script (বাংলা লিপি)",
        "ta-IN": "Tamil script (தமிழ் எழுத்து)",
        "te-IN": "Telugu script (తెలుగు లిపి)",
        "mr-IN": "Devanagari (देवनागरी)",
        "gu-IN": "Gujarati script (ગુજરાતી લિપિ)",
        "kn-IN": "Kannada script (ಕನ್ನಡ ಲಿಪಿ)",
        "ml-IN": "Malayalam script (മലയാളം ലിപി)",
        "od-IN": "Odia script (ଓଡ଼ିଆ ଅକ୍ଷର)",
        "pa-IN": "Gurmukhi script (ਗੁਰਮੁਖੀ ਲਿਪੀ)",
        "ur-IN": "Urdu script (اردو رسم الخط)",
        "en-IN": "English",
    }

    DOMAINS: Dict[str, Dict] = {
        "agriculture": {
            "icon": "🌾", "name": "Krishi Mitra",
            "description": "Farming advice, crop management, weather queries",
            "system_prompt": "You are Krishi Mitra, an agricultural expert. Help farmers with practical advice using simple language. Include local examples.",
        },
        "education": {
            "icon": "📚", "name": "Pathshala Tutor",
            "description": "Subject tutoring, exam preparation, concept explanation",
            "system_prompt": "You are Pathshala Tutor. Teach students patiently. Use analogies from daily life. Break down complex topics.",
        },
        "business": {
            "icon": "💼", "name": "Vyapar Saathi",
            "description": "Business documents, GST, quotations, formal letters",
            "system_prompt": "You are Vyapar Saathi, a business assistant. Help with professional documents, financial literacy, business planning.",
        },
        "career": {
            "icon": "🎯", "name": "Career Saarthi",
            "description": "Job preparation, resume writing, interview tips",
            "system_prompt": "You are Career Saarthi. Help job seekers prepare for interviews, improve resumes, build confidence.",
        },
        "daily_life": {
            "icon": "🏠", "name": "Griha Sahayak",
            "description": "Daily tasks, government schemes, how-to guides",
            "system_prompt": "You are Griha Sahayak. Help with everyday tasks like bill payment, form filling, scheme applications.",
        },
    }

    COMPLEXITY_GUIDELINES: Dict[str, str] = {
        "simple":  "Explain like talking to a 5th grader. Very simple words, short sentences, lots of examples.",
        "medium":  "Clear explanation suitable for a 10th grade student. Use some technical terms but explain them.",
        "complex": "Detailed, thorough explanation for someone with domain knowledge. Use proper terminology.",
    }


# ============================================================================
# SARVAM-30B CLIENT
# ============================================================================

class Sarvam30BClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }

    def _chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
        payload = {
            "model": Config.SARVAM_30B_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        resp = requests.post(
            Config.SARVAM_30B_URL,
            headers=self._headers,
            json=payload,
            timeout=Config.REQUEST_TIMEOUT,
        )
        if not resp.ok:
            raise Exception(f"Sarvam-30B error (HTTP {resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise Exception(f"Sarvam-30B returned empty content. Full response: {str(data)[:300]}")
        return content

    def understand_intent(self, user_query: str, user_language: str) -> Dict[str, Any]:
        system_prompt = (
            'Analyze the user query and return ONLY a JSON object with keys: '
            '"domain" (agriculture|education|business|career|daily_life), '
            '"complexity" (simple|medium|complex), '
            '"requires_document" (bool), "requires_calculation" (bool), '
            '"sentiment" (positive|neutral|urgent|confused), '
            '"entities" (list of strings).'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Language: {user_language}\nQuery: {user_query}"},
        ]
        default = {
            "domain": "daily_life", "complexity": "simple",
            "requires_document": False, "requires_calculation": False,
            "sentiment": "neutral", "entities": [],
        }
        try:
            raw = self._chat(messages, temperature=0.2)
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return default

    def generate_response(
        self,
        user_query: str,
        domain: str,
        user_language: str,
        lang_name: str,
        complexity_level: str = "simple",
        context: str = "",
    ) -> str:
        domain_cfg  = Config.DOMAINS.get(domain, Config.DOMAINS["daily_life"])
        guideline   = Config.COMPLEXITY_GUIDELINES.get(complexity_level, Config.COMPLEXITY_GUIDELINES["simple"])
        script_name = Config.LANGUAGE_SCRIPTS.get(user_language, lang_name)

        system_prompt = (
            f"{domain_cfg['system_prompt']}\n\n"
            f"RESPONSE GUIDELINES:\n"
            f"- Language: You MUST respond ONLY in {lang_name} ({script_name}).\n"
            f"- CRITICAL: Write EXCLUSIVELY in {script_name}. Do NOT use Roman/Latin transliteration. "
            f"Do NOT mix English words unless they are widely used technical terms with no native equivalent.\n"
            f"- Complexity: {guideline}\n"
            f"- Be warm, empathetic, and practical\n"
            f"- Include actionable steps if applicable\n"
            f"- Use local examples and analogies\n"
            f"- Keep response under 500 words for simple, 1000 for complex\n"
            f"\nADDITIONAL CONTEXT:\n{context}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"User's question: {user_query}\n\n"
                    f"IMPORTANT: Reply ONLY in {lang_name} using {script_name}. "
                    f"Do NOT write in Roman/English script. Use native {lang_name} script throughout."
                ),
            },
        ]
        temperature = 0.5 if complexity_level == "simple" else 0.7
        return self._chat(messages, temperature=temperature)


# ============================================================================
# SAARAS V3 CLIENT
# ============================================================================

class SaarasClient:
    MIME_MAP = {
        "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg",
        "flac": "audio/flac", "aac": "audio/aac", "m4a": "audio/mp4",
        "webm": "audio/webm",
    }

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, filename: str) -> Tuple[str, str]:
        ext = filename.rsplit('.', 1)[-1].lower()
        mime = self.MIME_MAP.get(ext, "audio/wav")
        resp = requests.post(
            Config.SAARAS_STT_URL,
            headers={"api-subscription-key": self.api_key},
            files={"file": (filename, io.BytesIO(audio_bytes), mime)},
            data={"model": Config.SAARAS_MODEL, "mode": "translate"},
            timeout=Config.REQUEST_TIMEOUT,
        )
        if not resp.ok:
            raise Exception(f"Saaras error: {resp.text}")
        result = resp.json()
        text = (result.get("transcript") or result.get("text") or "").strip()
        detected = result.get("language_code", "unknown")
        return text, detected


# ============================================================================
# MAYURA CLIENT
# ============================================================================

class MayuraClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }

    def simplify(self, text: str, target_language: str, gender: str = "Female") -> str:
        payload = {
            "input": text,
            "source_language_code": "auto",
            "target_language_code": target_language,
            "speaker_gender": gender,
            "mode": "modern-colloquial",
            "model": Config.MAYURA_MODEL,
            "numerals_format": "international",
        }
        resp = requests.post(
            Config.MAYURA_URL,
            headers=self._headers,
            json=payload,
            timeout=Config.REQUEST_TIMEOUT,
        )
        if not resp.ok:
            raise Exception(f"Mayura error: {resp.text}")
        result = resp.json()
        return result.get("translated_text") or result.get("result") or ""

    def chunked_simplify(self, text: str, target_language: str, gender: str = "Female", chunk_size: int = 900) -> str:
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        return " ".join(self.simplify(c, target_language, gender) for c in chunks if c.strip())


# ============================================================================
# BULBUL TTS CLIENT
# ============================================================================

class BulbulTTSClient:
    # Default speakers per language for Bulbul v2
    LANGUAGE_SPEAKERS: Dict[str, str] = {
        "hi-IN": "vidya",
        "en-IN": "vidya",
        "bn-IN": "aarav",
        "ta-IN": "thilaga",
        "te-IN": "pavithra",
        "kn-IN": "vidya",
        "ml-IN": "sobhana",
        "mr-IN": "meera",
        "gu-IN": "meera",
        "od-IN": "meera",
        "pa-IN": "meera",
        "ur-IN": "meera",
    }

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }

    def speak(self, text: str, language: str, speaker: str = None) -> Optional[bytes]:
        # Pick the right speaker for the language
        if speaker is None:
            speaker = self.LANGUAGE_SPEAKERS.get(language, "meera")

        chunks = [text[i:i + Config.TTS_CHUNK_SIZE] for i in range(0, len(text), Config.TTS_CHUNK_SIZE)]
        audio_parts = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            resp = requests.post(
                Config.BULBUL_TTS_URL,
                headers=self._headers,
                json={"inputs": [chunk], "target_language_code": language, "speaker": speaker, "model": Config.TTS_MODEL},
                timeout=30,
            )
            if not resp.ok:
                raise Exception(f"Bulbul TTS error (HTTP {resp.status_code}): {resp.text[:300]}")
            audios = resp.json().get("audios", [])
            if audios:
                audio_parts.append(base64.b64decode(audios[0]))
        return b"".join(audio_parts) if audio_parts else None


# ============================================================================
# STREAMLIT APP
# ============================================================================

def _init_session():
    if "session_init" not in st.session_state:
        st.session_state.session_init   = True
        st.session_state.conversations  = []
        st.session_state.total_queries  = 0
        st.session_state.current_domain = "daily_life"


def main():
    st.set_page_config(
        page_title="Manthan - Voice AI for Everyone",
        page_icon="🗣️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&display=swap');
    .main { font-family: 'Noto Sans Devanagari', sans-serif; }
    .hero {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem; border-radius: 1rem; color: white; text-align: center; margin-bottom: 2rem;
    }
    .hero h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
    .hero p  { font-size: 1.2rem; opacity: 0.9; }
    .response-card {
        background: #f0fdf4; border-left: 4px solid #22c55e;
        padding: 1.5rem; border-radius: 0.5rem; margin: 1rem 0; font-size: 1.1rem; line-height: 1.6;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="hero">
        <h1>🗣️ Manthan — एक मुलाकात, अनेक भाषा</h1>
        <p>Your AI Friend Who Speaks Your Language | आपकी भाषा में आपका AI साथी</p>
    </div>
    """, unsafe_allow_html=True)

    _init_session()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        api_key = st.text_input("Sarvam API Key", type="password", placeholder="Enter your API key")

        st.markdown("---")
        user_language = st.selectbox(
            "🌐 Your Language / आपकी भाषा",
            options=list(Config.LANGUAGES.keys()),
            format_func=lambda x: Config.LANGUAGES[x],
        )
        complexity = st.select_slider(
            "📊 Explanation Complexity",
            options=["simple", "medium", "complex"],
            value="simple",
            format_func=lambda x: {"simple": "Simple (सरल)", "medium": "Medium (मध्यम)", "complex": "Complex (विस्तृत)"}[x],
        )

        st.markdown("---")
        st.markdown("### 🤖 Powered By")
        st.markdown("- **Sarvam-30B** — Brain\n- **Saaras v3** — Ear (STT)\n- **Mayura v1** — Simplifier\n- **Bulbul v2** — Voice (TTS)")

        st.markdown("---")
        st.markdown("### 📊 Session Stats")
        st.metric("Conversations", len(st.session_state.conversations))
        st.metric("Total Queries",  st.session_state.total_queries)

    if not api_key:
        st.warning("⚠️ Please enter your Sarvam API key in the sidebar to continue.")
        st.stop()

    # Instantiate clients once per run (cheap — no network calls)
    sarvam30b = Sarvam30BClient(api_key)
    saaras    = SaarasClient(api_key)
    mayura    = MayuraClient(api_key)
    tts       = BulbulTTSClient(api_key)

    # ── Domain Selection ──────────────────────────────────────────────────────
    st.markdown("### 🎯 What can I help you with?")
    cols = st.columns(len(Config.DOMAINS))
    for col, (domain_key, domain_data) in zip(cols, Config.DOMAINS.items()):
        with col:
            if st.button(f"{domain_data['icon']}\n\n{domain_data['name']}", use_container_width=True, key=f"domain_{domain_key}"):
                st.session_state.current_domain = domain_key

    current_domain = st.session_state.current_domain
    domain_data    = Config.DOMAINS[current_domain]
    st.info(f"**{domain_data['icon']} {domain_data['name']}** — {domain_data['description']}")

    st.markdown("---")

    # ── Input ─────────────────────────────────────────────────────────────────
    st.markdown("### 🎤 Ask me anything / कुछ भी पूछिए")
    col1, col2 = st.columns(2)
    query_text = ""

    with col1:
        st.markdown("**Type your question**")
        query_text = st.text_area(
            "", height=150, key="text_input",
            placeholder="How do I improve soil quality?\nमेरी फसल में कीड़े लग गए, क्या करूं?",
        )

    with col2:
        st.markdown("**Or speak / या बोलें**")
        audio_input = st.audio_input("Record your question")
        if audio_input:
            audio_bytes = audio_input.read()
            st.audio(audio_bytes, format="audio/wav")
            with st.spinner("🎙️ Listening..."):
                try:
                    transcribed, detected = saaras.transcribe(audio_bytes, "query.wav")
                    query_text = transcribed
                    st.success(f"🎤 Heard: {transcribed[:100]}{'...' if len(transcribed) > 100 else ''}")
                    if detected not in ("unknown", user_language) and detected in Config.LANGUAGES:
                        st.info(f"🔍 Detected: {Config.LANGUAGES[detected]}")
                except Exception as e:
                    st.error(f"Transcription failed: {e}")

    # ── Processing ────────────────────────────────────────────────────────────
    if query_text.strip():
        st.markdown("---")
        with st.spinner("🧠 Sarvam-30B is reasoning..."):
            try:
                lang_name = Config.LANGUAGES[user_language]

                intent = sarvam30b.understand_intent(query_text, lang_name)

                # ✅ FIX: pass both user_language (code) and lang_name (native name)
                response = sarvam30b.generate_response(
                    user_query=query_text,
                    domain=current_domain,
                    user_language=user_language,
                    lang_name=lang_name,
                    complexity_level=complexity,
                    context=f"Intent: {json.dumps(intent)}",
                )

                # Simplify only if needed
                if not response:
                    raise Exception("Sarvam-30B returned an empty response. Please try again.")
                final_response = response
                if complexity == "simple" and len(response) > 300:
                    with st.spinner("🗣️ Simplifying language..."):
                        try:
                            final_response = mayura.simplify(response, user_language)
                        except Exception:
                            pass  # fall back to original response

                # TTS
                audio_response = None
                with st.spinner("🔊 Preparing voice response..."):
                    try:
                        audio_response = tts.speak(final_response, user_language)
                        if not audio_response:
                            st.warning("⚠️ TTS returned no audio data.")
                    except Exception as tts_err:
                        st.warning(f"⚠️ Voice response unavailable: {tts_err}")

                # ── Display ───────────────────────────────────────────────────
                st.markdown("### 💬 Response / उत्तर")
                st.markdown(f'<div class="response-card">{final_response}</div>', unsafe_allow_html=True)

                if audio_response:
                    st.audio(audio_response, format="audio/wav", autoplay=True)
                    st.caption("🔊 Voice response ready")

                with st.expander("🔍 How I understood your query"):
                    st.json(intent)

                # Save history
                st.session_state.conversations.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "domain": current_domain,
                    "query": query_text,
                    "response": final_response,
                    "intent": intent,
                })
                st.session_state.total_queries += 1

                # Downloads
                dl1, dl2, dl3 = st.columns(3)
                with dl1:
                    st.download_button(
                        "📝 Download Response", final_response,
                        file_name=f"manthan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                    )
                if final_response != response:
                    with dl2:
                        st.download_button(
                            "🔄 Simplified Version", final_response,
                            file_name="simplified.txt", mime="text/plain",
                        )
                if audio_response:
                    with dl3:
                        st.download_button(
                            "🔊 Download Audio", audio_response,
                            file_name="voice_response.wav", mime="audio/wav",
                        )

            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.exception(e)

    # ── History ───────────────────────────────────────────────────────────────
    if st.session_state.conversations:
        st.markdown("---")
        st.markdown("### 📜 Conversation History")
        for conv in reversed(st.session_state.conversations[-10:]):
            with st.expander(f"{conv['timestamp']} — {conv['domain']}"):
                st.markdown(f"**You:** {conv['query'][:200]}")
                st.markdown(f"**Manthan:** {conv['response'][:300]}")

    st.markdown("---")
    st.markdown("""
    <div style="text-align:center;color:#666;padding:2rem;">
        <p>🇮🇳 <strong>Manthan</strong> — Breaking language barriers with AI</p>
        <p>Powered by Sarvam AI • Made in India • For Every Indian</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()