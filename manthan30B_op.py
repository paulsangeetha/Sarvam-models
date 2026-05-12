"""
===============================================================================
PROJECT MANTHAN - Voice AI for Every Indian
Complete working code - Just copy, paste, and run!
===============================================================================
"""

import io
import base64
import json
import re
import time
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

import streamlit as st
import requests

# ============================================================================
# CONFIGURATION
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
        "hi-IN": "हिन्दी",
        "bn-IN": "বাংলা",
        "ta-IN": "தமிழ்",
        "te-IN": "తెలుగు",
        "mr-IN": "मराठी",
        "gu-IN": "ગુજરાતી",
        "kn-IN": "ಕನ್ನಡ",
        "ml-IN": "മലയാളം",
        "od-IN": "ଓଡ଼ିଆ",
        "pa-IN": "ਪੰਜਾਬੀ",
        "ur-IN": "اُردُو",
        "en-IN": "English",
    }

    LANGUAGE_SCRIPTS: Dict[str, str] = {
        "hi-IN": "Devanagari",
        "bn-IN": "Bengali",
        "ta-IN": "Tamil",
        "te-IN": "Telugu",
        "mr-IN": "Devanagari",
        "gu-IN": "Gujarati",
        "kn-IN": "Kannada",
        "ml-IN": "Malayalam",
        "od-IN": "Odia",
        "pa-IN": "Gurmukhi",
        "ur-IN": "Urdu",
        "en-IN": "English",
    }

    DOMAINS: Dict[str, Dict] = {
        "agriculture": {
            "icon": "🌾",
            "name": "Krishi Mitra",
            "description": "Farming advice, crop management, weather queries",
            "system_prompt": "You are Krishi Mitra, an agricultural expert. Help farmers with practical advice using simple language.",
        },
        "education": {
            "icon": "📚",
            "name": "Pathshala Tutor",
            "description": "Subject tutoring, exam preparation, concept explanation",
            "system_prompt": "You are Pathshala Tutor. Teach students patiently. Use analogies from daily life.",
        },
        "business": {
            "icon": "💼",
            "name": "Vyapar Saathi",
            "description": "Business documents, GST, quotations, formal letters",
            "system_prompt": "You are Vyapar Saathi, a business assistant. Help with professional documents.",
        },
        "career": {
            "icon": "🎯",
            "name": "Career Saarthi",
            "description": "Job preparation, resume writing, interview tips",
            "system_prompt": "You are Career Saarthi. Help job seekers prepare for interviews, improve resumes.",
        },
        "daily_life": {
            "icon": "🏠",
            "name": "Griha Sahayak",
            "description": "Daily tasks, government schemes, how-to guides",
            "system_prompt": "You are Griha Sahayak. Help with everyday tasks like bill payment, form filling.",
        },
    }

    COMPLEXITY_GUIDELINES: Dict[str, str] = {
        "simple": "Explain like talking to a 5th grader. Very simple words, short sentences.",
        "medium": "Clear explanation suitable for a 10th grade student.",
        "complex": "Detailed, thorough explanation for someone with domain knowledge.",
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
        
        response = requests.post(
            Config.SARVAM_30B_URL,
            headers=self._headers,
            json=payload,
            timeout=Config.REQUEST_TIMEOUT,
        )
        
        if not response.ok:
            raise Exception(f"Sarvam-30B error: {response.text[:200]}")
        
        data = response.json()
        
        # Handle both 'content' and 'reasoning_content' fields
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content")
        
        if content is None:
            content = message.get("reasoning_content")
        
        if not content:
            raise Exception(f"No content in response: {str(data)[:200]}")
        
        return content.strip()

    def understand_intent(self, user_query: str, user_language: str) -> Dict[str, Any]:
        system_prompt = """Analyze the user query and return ONLY a JSON object with keys:
        "domain" (agriculture|education|business|career|daily_life),
        "complexity" (simple|medium|complex),
        "sentiment" (positive|neutral|urgent|confused)
        Return ONLY the JSON, no other text."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Language: {user_language}\nQuery: {user_query}"},
        ]
        
        default = {"domain": "daily_life", "complexity": "simple", "sentiment": "neutral"}
        
        try:
            raw = self._chat(messages, temperature=0.2, max_tokens=200)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return default
        except Exception:
            return default

    def generate_response(
        self,
        user_query: str,
        domain: str,
        user_language: str,
        lang_name: str,
        complexity_level: str = "simple",
    ) -> str:
        domain_cfg = Config.DOMAINS.get(domain, Config.DOMAINS["daily_life"])
        guideline = Config.COMPLEXITY_GUIDELINES.get(complexity_level, Config.COMPLEXITY_GUIDELINES["simple"])
        
        system_prompt = f"""{domain_cfg['system_prompt']}

CRITICAL INSTRUCTIONS:
1. Respond ONLY in {lang_name} language
2. Use {Config.LANGUAGE_SCRIPTS.get(user_language, 'native script')} script
3. Complexity: {guideline}
4. Keep response under 300 words
5. Be warm and helpful

User query: {user_query}

Provide your response in {lang_name} now:"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]
        
        temperature = 0.3 if complexity_level == "simple" else 0.6
        return self._chat(messages, temperature=temperature)


# ============================================================================
# SAARAS STT CLIENT
# ============================================================================

class SaarasClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, filename: str) -> Tuple[str, str]:
        mime_map = {
            "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg",
            "webm": "audio/webm", "m4a": "audio/mp4"
        }
        ext = filename.split('.')[-1].lower()
        mime = mime_map.get(ext, "audio/wav")
        
        response = requests.post(
            Config.SAARAS_STT_URL,
            headers={"api-subscription-key": self.api_key},
            files={"file": (filename, io.BytesIO(audio_bytes), mime)},
            data={"model": Config.SAARAS_MODEL},
            timeout=Config.REQUEST_TIMEOUT,
        )
        
        if not response.ok:
            raise Exception(f"STT error: {response.text}")
        
        result = response.json()
        text = result.get("transcript", "").strip()
        language = result.get("language_code", "unknown")
        return text, language


# ============================================================================
# BULBUL TTS CLIENT
# ============================================================================

class BulbulTTSClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }
    
    def speak(self, text: str, language: str) -> Optional[bytes]:
        speakers = {
            "hi-IN": "vidya", "en-IN": "vidya", "ta-IN": "thilaga",
            "te-IN": "pavithra", "bn-IN": "aarav", "kn-IN": "vidya"
        }
        speaker = speakers.get(language, "meera")
        
        # Split long text into chunks
        chunks = [text[i:i+450] for i in range(0, len(text), 450)]
        audio_parts = []
        
        for chunk in chunks:
            if not chunk.strip():
                continue
                
            response = requests.post(
                Config.BULBUL_TTS_URL,
                headers=self._headers,
                json={
                    "inputs": [chunk],
                    "target_language_code": language,
                    "speaker": speaker,
                    "model": Config.TTS_MODEL
                },
                timeout=30,
            )
            
            if not response.ok:
                continue
                
            audios = response.json().get("audios", [])
            if audios:
                audio_parts.append(base64.b64decode(audios[0]))
        
        return b"".join(audio_parts) if audio_parts else None


# ============================================================================
# MAIN STREAMLIT APP
# ============================================================================

def init_session():
    if "conversations" not in st.session_state:
        st.session_state.conversations = []
        st.session_state.total_queries = 0
        st.session_state.current_domain = "daily_life"

def main():
    st.set_page_config(
        page_title="Manthan - Voice AI for India",
        page_icon="🗣️",
        layout="wide"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .hero {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .response-card {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Hero section
    st.markdown("""
    <div class="hero">
        <h1>🗣️ Manthan — Voice AI for Every Indian</h1>
        <p>Ask questions in your language • Get answers in voice</p>
    </div>
    """, unsafe_allow_html=True)
    
    init_session()
    
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        api_key = st.text_input("Sarvam API Key", type="password", placeholder="Enter your API key")
        
        st.markdown("---")
        user_language = st.selectbox(
            "🌐 Your Language",
            options=list(Config.LANGUAGES.keys()),
            format_func=lambda x: Config.LANGUAGES[x]
        )
        
        complexity = st.select_slider(
            "📊 Complexity",
            options=["simple", "medium", "complex"],
            value="simple",
            format_func=lambda x: {"simple": "Simple", "medium": "Medium", "complex": "Complex"}[x]
        )
        
        st.markdown("---")
        st.markdown("### 📊 Stats")
        st.metric("Conversations", len(st.session_state.conversations))
        st.metric("Total Queries", st.session_state.total_queries)
        
        st.markdown("---")
        st.markdown("### 🤖 Powered by")
        st.markdown("- Sarvam-30B (AI)")
        st.markdown("- Saaras (STT)")
        st.markdown("- Bulbul (TTS)")
    
    if not api_key:
        st.warning("⚠️ Please enter your Sarvam API key in the sidebar to continue.")
        st.stop()
    
    # Initialize clients
    sarvam = Sarvam30BClient(api_key)
    stt = SaarasClient(api_key)
    tts = BulbulTTSClient(api_key)
    
    # Domain selection
    st.markdown("## 🎯 Choose your domain")
    cols = st.columns(len(Config.DOMAINS))
    for col, (domain_key, domain_data) in zip(cols, Config.DOMAINS.items()):
        with col:
            if st.button(f"{domain_data['icon']}\n{domain_data['name']}", use_container_width=True):
                st.session_state.current_domain = domain_key
    
    current_domain = st.session_state.current_domain
    domain_data = Config.DOMAINS[current_domain]
    st.info(f"**{domain_data['icon']} {domain_data['name']}** — {domain_data['description']}")
    
    st.markdown("---")
    
    # Input section
    st.markdown("## 🎤 Ask your question")
    col1, col2 = st.columns(2)
    
    query_text = ""
    
    with col1:
        st.markdown("**Type your question**")
        query_text = st.text_area("", height=120, placeholder="Example: How do I grow wheat? / गेहूं कैसे उगाएं?")
    
    with col2:
        st.markdown("**Or speak**")
        audio_input = st.audio_input("Record your question")
        if audio_input:
            audio_bytes = audio_input.read()
            st.audio(audio_bytes, format="audio/wav")
            with st.spinner("🎙️ Transcribing..."):
                try:
                    transcribed, detected = stt.transcribe(audio_bytes, "audio.wav")
                    query_text = transcribed
                    st.success(f"🗣️ You said: {transcribed}")
                except Exception as e:
                    st.error(f"Transcription failed: {e}")
    
    # Process query
    if query_text and query_text.strip():
        st.markdown("---")
        
        with st.spinner("🤔 Thinking..."):
            try:
                lang_name = Config.LANGUAGES[user_language]
                
                # Understand intent
                intent = sarvam.understand_intent(query_text, lang_name)
                
                # Generate response
                response = sarvam.generate_response(
                    user_query=query_text,
                    domain=current_domain,
                    user_language=user_language,
                    lang_name=lang_name,
                    complexity_level=complexity
                )
                
                # Generate voice
                audio_response = None
                with st.spinner("🔊 Generating voice..."):
                    try:
                        audio_response = tts.speak(response, user_language)
                    except Exception as e:
                        st.warning(f"Voice generation failed: {e}")
                
                # Display response
                st.markdown("## 💬 Response")
                st.markdown(f'<div class="response-card">{response}</div>', unsafe_allow_html=True)
                
                if audio_response:
                    st.audio(audio_response, format="audio/wav", autoplay=True)
                    st.caption("🔊 Voice response ready")
                
                # Show intent in expander
                with st.expander("🔍 How I understood your query"):
                    st.json(intent)
                
                # Save to history
                st.session_state.conversations.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "domain": current_domain,
                    "query": query_text,
                    "response": response
                })
                st.session_state.total_queries += 1
                
                # Download buttons
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📝 Download Response",
                        response,
                        file_name=f"manthan_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    )
                if audio_response:
                    with col2:
                        st.download_button(
                            "🔊 Download Audio",
                            audio_response,
                            file_name="voice_response.wav",
                            mime="audio/wav"
                        )
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.exception(e)
    
    # Conversation history
    if st.session_state.conversations:
        st.markdown("---")
        st.markdown("## 📜 Recent Conversations")
        for conv in reversed(st.session_state.conversations[-5:]):
            with st.expander(f"{conv['timestamp']} - {conv['domain']}"):
                st.markdown(f"**You:** {conv['query'][:200]}")
                st.markdown(f"**Manthan:** {conv['response'][:300]}...")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 2rem;">
        <p>🇮🇳 <strong>Manthan</strong> — Breaking language barriers with AI</p>
        <p>Powered by Sarvam AI • Made in India</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()