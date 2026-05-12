"""
================================================================================
SARVAM-105B - Voice AI for Every Indian
Using Sarvam-105B (105 billion parameters - more powerful than 30B)
================================================================================
"""

import io
import re
import time
import json
import base64
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

import streamlit as st
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    # API Endpoints
    SAARAS_STT_URL = "https://api.sarvam.ai/speech-to-text"
    SARVAM_LLM_URL = "https://api.sarvam.ai/v1/chat/completions"
    SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"
    MAYURA_URL = "https://api.sarvam.ai/translate"
    BULBUL_TTS_URL = "https://api.sarvam.ai/text-to-speech"
    
    # Models - CORRECTED NAMES
    SAARAS_MODEL = "saaras:v3"
    SARVAM_LLM_MODEL = "sarvam-105b"  # ← CORRECT: 105B parameters
    SARVAM_TRANSLATE_MODEL = "sarvam-translate:v1"
    MAYURA_MODEL = "mayura:v1"
    TTS_MODEL = "bulbul:v2"
    
    # Alternate models available: sarvam-30b, sarvam-m, sarvam-105b
    # You can switch by changing SARVAM_LLM_MODEL above
    
    # Limits
    MAX_AUDIO_SEC = 30
    MAX_LLM_TOKENS = 4096
    REQUEST_TIMEOUT = 120
    TTS_CHUNK_SIZE = 450
    COST_PER_10K = 20
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    
    SOURCE_LANG = "en-IN"
    
    # Supported languages
    LANGUAGES: Dict[str, str] = {
        "hi-IN": "हिन्दी (Hindi)",
        "bn-IN": "বাংলা (Bengali)",
        "ta-IN": "தமிழ் (Tamil)",
        "te-IN": "తెలుగు (Telugu)",
        "mr-IN": "मराठी (Marathi)",
        "gu-IN": "ગુજરાતી (Gujarati)",
        "kn-IN": "ಕನ್ನಡ (Kannada)",
        "ml-IN": "മലയാളം (Malayalam)",
        "od-IN": "ଓଡ଼ିଆ (Odia)",
        "pa-IN": "ਪੰਜਾਬੀ (Punjabi)",
        "as-IN": "অসমীয়া (Assamese)",
        "ur-IN": "اُردُو (Urdu)",
        "mai-IN": "मैथिली (Maithili)",
        "sat-IN": "ᱥᱟᱱᱛᱟᱲᱤ (Santali)",
        "ks-IN": "कॉशुर (Kashmiri)",
        "ne-IN": "नेपाली (Nepali)",
        "sd-IN": "سنڌي (Sindhi)",
        "kok-IN": "कोंकणी (Konkani)",
        "dgo-IN": "डोगरी (Dogri)",
        "brx-IN": "बर' (Bodo)",
        "mni-IN": "মৈতৈলোন্ (Manipuri)",
        "sa-IN": "संस्कृतम् (Sanskrit)",
    }
    
    # Mayura supported (11 languages)
    MAYURA_SUPPORTED: Dict[str, str] = {
        k: v for k, v in LANGUAGES.items() if k in {
            "hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN",
            "kn-IN", "ml-IN", "od-IN", "pa-IN", "ur-IN"
        }
    }
    
    LANGUAGE_SCRIPTS: Dict[str, str] = {
        "hi-IN": "Devanagari", "bn-IN": "Bengali", "ta-IN": "Tamil",
        "te-IN": "Telugu", "mr-IN": "Devanagari", "gu-IN": "Gujarati",
        "kn-IN": "Kannada", "ml-IN": "Malayalam", "od-IN": "Odia",
        "pa-IN": "Gurmukhi", "ur-IN": "Urdu", "en-IN": "English",
    }
    
    # Domains with improved prompts for 105B
    DOMAINS: Dict[str, Dict] = {
        "agriculture": {
            "icon": "🌾", "name": "Krishi Mitra",
            "description": "Farming advice, crop management, weather queries",
            "system_prompt": """You are Krishi Mitra, an expert agricultural advisor with deep knowledge of Indian farming. 
            Provide practical, actionable advice. Use simple language with examples from real farming situations.
            Include specific recommendations for crops, soil, pests, and weather adaptation.
            Always respond in the user's language with cultural sensitivity."""
        },
        "education": {
            "icon": "📚", "name": "Pathshala Tutor",
            "description": "Subject tutoring, concept explanation",
            "system_prompt": """You are Pathshala Tutor, an expert teacher. Explain concepts clearly with examples from daily life.
            Break down complex topics into simple steps. Encourage learning with positive reinforcement.
            Always respond in the user's language."""
        },
        "business": {
            "icon": "💼", "name": "Vyapar Saathi",
            "description": "Business documents, GST, quotations",
            "system_prompt": """You are Vyapar Saathi, a business consultant. Provide professional, accurate advice for 
            small business owners. Help with documentation, compliance, and financial matters.
            Always respond in the user's language."""
        },
        "career": {
            "icon": "🎯", "name": "Career Saarthi",
            "description": "Job preparation, resume writing, interview tips",
            "system_prompt": """You are Career Saarthi, a career counselor. Provide practical job search advice,
            interview preparation tips, and resume improvement suggestions tailored to Indian job market.
            Always respond in the user's language."""
        },
        "daily_life": {
            "icon": "🏠", "name": "Griha Sahayak",
            "description": "Daily tasks, government schemes, how-to guides",
            "system_prompt": """You are Griha Sahayak, a helpful assistant for everyday tasks. Provide step-by-step guidance
            for common tasks like bill payment, form filling, accessing government services.
            Always respond in the user's language."""
        },
        "legal": {
            "icon": "⚖️", "name": "Nyaya Mitra",
            "description": "Legal rights, document understanding",
            "system_prompt": """You are Nyaya Mitra, a legal literacy assistant. Explain legal concepts in simple language.
            Help citizens understand their rights. Never give legal advice that requires a lawyer, but explain processes.
            Always respond in the user's language."""
        },
    }
    
    DOC_TYPES: Dict[str, str] = {
        "court_notice": "⚖️ Court Notice",
        "land_deed": "🏡 Land Deed / Mutation",
        "fir": "🚨 FIR / Police Report",
        "rti": "📋 RTI Application",
        "govt_order": "📜 Government Order",
        "other": "📄 Other Document",
    }
    
    SUBJECTS: Dict[str, str] = {
        "physics": "⚛️ Physics", "chemistry": "🧪 Chemistry",
        "biology": "🌱 Biology", "maths": "📐 Mathematics",
        "history": "📜 History", "geography": "🌍 Geography",
        "civics": "⚖️ Civics", "economics": "📊 Economics",
        "english": "📖 English Literature", "other": "📚 Other",
    }
    
    COMPLEXITY_GUIDELINES: Dict[str, str] = {
        "simple": "Explain like talking to a 5th grader. Very simple words, short sentences, use analogies.",
        "medium": "Clear explanation suitable for a 10th grade student. Include some details but keep accessible.",
        "complex": "Detailed, thorough explanation for someone with domain knowledge. Include nuances and examples.",
    }

config = Config()


# ============================================================================
# SARVAM-105B CLIENT (Main AI Model)
# ============================================================================

class Sarvam105BClient:
    """Client for Sarvam-105B LLM - 105 billion parameters - India's largest multilingual model"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }
    
    def _chat_with_retry(self, messages: List[Dict], temperature: float = 0.7, 
                          max_tokens: int = 4096, retry_count: int = 0) -> str:
        """Make API call with retry logic"""
        payload = {
            "model": config.SARVAM_LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        
        try:
            response = requests.post(
                config.SARVAM_LLM_URL,
                headers=self._headers,
                json=payload,
                timeout=config.REQUEST_TIMEOUT,
            )
            
            if response.status_code == 429:  # Rate limit
                if retry_count < config.MAX_RETRIES:
                    wait_time = config.RETRY_DELAY * (retry_count + 1)
                    st.warning(f"Rate limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    return self._chat_with_retry(messages, temperature, max_tokens, retry_count + 1)
                else:
                    raise Exception("Rate limit exceeded. Please wait a moment and try again.")
            
            if not response.ok:
                error_detail = response.text[:500]
                raise Exception(f"Sarvam API error ({response.status_code}): {error_detail}")
            
            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content") or message.get("reasoning_content")
            
            if not content:
                raise Exception(f"No content in response: {str(data)[:200]}")
            
            return content.strip()
            
        except requests.exceptions.Timeout:
            if retry_count < config.MAX_RETRIES:
                st.warning(f"Request timeout. Retrying ({retry_count + 1}/{config.MAX_RETRIES})...")
                time.sleep(config.RETRY_DELAY)
                return self._chat_with_retry(messages, temperature, max_tokens, retry_count + 1)
            raise Exception("Request timeout. The model may be busy. Please try a simpler question.")
        
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to Sarvam API. Please check your internet connection.")
    
    def generate_response(self, user_query: str, domain: str, user_language: str,
                          lang_name: str, complexity_level: str = "simple",
                          conversation_history: Optional[List[Dict]] = None) -> str:
        """Generate response using Sarvam-105B with context awareness"""
        
        domain_cfg = config.DOMAINS.get(domain, config.DOMAINS["daily_life"])
        guideline = config.COMPLEXITY_GUIDELINES.get(complexity_level, config.COMPLEXITY_GUIDELINES["simple"])
        
        system_prompt = f"""{domain_cfg['system_prompt']}

IMPORTANT INSTRUCTIONS:
1. Respond ONLY in {lang_name} language
2. Use {config.LANGUAGE_SCRIPTS.get(user_language, 'native script')} script
3. Complexity: {guideline}
4. Keep response clear and well-structured, but not overly long
5. Be warm, helpful, and culturally appropriate for India
6. If unsure, say so honestly

User query: {user_query}

Now provide your response in {lang_name}:"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history if provided (for context)
        if conversation_history:
            for hist in conversation_history[-6:]:  # Last 6 exchanges
                messages.append({"role": "user", "content": hist.get("query", "")})
                messages.append({"role": "assistant", "content": hist.get("response", "")})
        
        messages.append({"role": "user", "content": user_query})
        
        temperature = 0.3 if complexity_level == "simple" else 0.6
        
        return self._chat_with_retry(messages, temperature=temperature, max_tokens=2048)
    
    def understand_intent(self, user_query: str, user_language: str) -> Dict[str, Any]:
        """Use 105B to understand user intent"""
        system_prompt = """Analyze the user query and return ONLY a JSON object with keys:
        "domain" (agriculture|education|business|career|daily_life|legal),
        "complexity" (simple|medium|complex),
        "sentiment" (positive|neutral|urgent|confused),
        "key_topics" (list of 2-3 main topics as strings),
        "needs_clarification" (boolean)
        Return ONLY the JSON, no other text."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Language: {user_language}\nQuery: {user_query}"},
        ]
        
        default = {"domain": "daily_life", "complexity": "simple", 
                   "sentiment": "neutral", "key_topics": [], "needs_clarification": False}
        
        try:
            raw = self._chat_with_retry(messages, temperature=0.2, max_tokens=300)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {**default, **result}
            return default
        except Exception:
            return default


# ============================================================================
# SAARAS STT CLIENT
# ============================================================================

class SaarasClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def transcribe(self, audio_bytes: bytes, filename: str, 
                   language_code: str = "unknown", mode: str = "translate") -> Tuple[str, str]:
        ext = filename.split('.')[-1].lower()
        mime_map = {
            "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg",
            "webm": "audio/webm", "m4a": "audio/mp4", "flac": "audio/flac"
        }
        mime = mime_map.get(ext, "audio/wav")
        
        files = {"file": (filename, io.BytesIO(audio_bytes), mime)}
        data = {"model": config.SAARAS_MODEL, "mode": mode}
        if language_code and language_code != "unknown":
            data["language_code"] = language_code
        
        for attempt in range(config.MAX_RETRIES):
            try:
                response = requests.post(
                    config.SAARAS_STT_URL,
                    headers={"api-subscription-key": self.api_key},
                    files=files,
                    data=data,
                    timeout=config.REQUEST_TIMEOUT,
                )
                if response.ok:
                    break
            except requests.exceptions.Timeout:
                if attempt == config.MAX_RETRIES - 1:
                    raise Exception("STT timeout after retries")
                time.sleep(config.RETRY_DELAY)
        
        if not response.ok:
            raise Exception(f"STT error: {response.text[:200]}")
        
        result = response.json()
        text = result.get("transcript", "").strip()
        detected = result.get("language_code", language_code)
        return text, detected


# ============================================================================
# BULBUL TTS CLIENT
# ============================================================================

class BulbulClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "api-subscription-key": api_key,
        }
    
    def speak(self, text: str, language: str) -> Optional[bytes]:
        speakers = {
            "hi-IN": "vidya", "en-IN": "vidya", "ta-IN": "thilaga",
            "te-IN": "pavithra", "bn-IN": "aarav", "kn-IN": "vidya",
            "ml-IN": "meera", "mr-IN": "arvind", "gu-IN": "arvind",
            "pa-IN": "arvind", "od-IN": "arvind"
        }
        speaker = speakers.get(language, "meera")
        
        chunks = [text[i:i+450] for i in range(0, len(text), 450)]
        audio_parts = []
        
        for chunk in chunks:
            if not chunk.strip():
                continue
            for attempt in range(config.MAX_RETRIES):
                try:
                    response = requests.post(
                        config.BULBUL_TTS_URL,
                        headers=self._headers,
                        json={
                            "inputs": [chunk],
                            "target_language_code": language,
                            "speaker": speaker,
                            "model": config.TTS_MODEL
                        },
                        timeout=30,
                    )
                    if response.ok:
                        break
                except requests.exceptions.Timeout:
                    if attempt == config.MAX_RETRIES - 1:
                        continue
                    time.sleep(config.RETRY_DELAY)
            
            if response.ok:
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
    if "total_queries" not in st.session_state:
        st.session_state.total_queries = 0
    if "current_domain" not in st.session_state:
        st.session_state.current_domain = "daily_life"
    if "total_chars" not in st.session_state:
        st.session_state.total_chars = 0


def get_model_display_name() -> str:
    model = config.SARVAM_LLM_MODEL
    if model == "sarvam-105b":
        return "Sarvam-105B (105 Billion Parameters)"
    elif model == "sarvam-30b":
        return "Sarvam-30B (30 Billion Parameters)"
    elif model == "sarvam-m":
        return "Sarvam-M"
    return model


def main():
    st.set_page_config(
        page_title="Bharat Vaani - Sarvam 105B Voice AI",
        page_icon="🇮🇳",
        layout="wide"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .hero {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .hero h1 {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .hero-badge {
        background: #e94560;
        display: inline-block;
        padding: 0.25rem 1rem;
        border-radius: 2rem;
        font-size: 0.8rem;
        margin-top: 0.5rem;
    }
    .response-card {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
        font-size: 1.1rem;
        line-height: 1.6;
    }
    .info-box {
        background: #e0f2fe;
        border-left: 4px solid #0284c7;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Hero section with correct model name
    st.markdown(f"""
    <div class="hero">
        <h1>🇮🇳 Bharat Vaani — भारत वाणी</h1>
        <p>Voice AI for Every Indian | Powered by Sarvam AI</p>
        <div class="hero-badge">🧠 {get_model_display_name()} • 22 Languages • Real-time Voice</div>
    </div>
    """, unsafe_allow_html=True)
    
    init_session()
    
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        api_key = st.text_input("Sarvam API Key", 
                                type="password", 
                                placeholder="Enter your API key")
        
        st.markdown("---")
        
        # Model selector
        st.markdown("### 🧠 Model Selection")
        model_choice = st.selectbox(
            "Choose LLM Model",
            options=["sarvam-105b", "sarvam-30b", "sarvam-m"],
            format_func=lambda x: {
                "sarvam-105b": "Sarvam-105B (Most Powerful - 105B params)",
                "sarvam-30b": "Sarvam-30B (Faster - 30B params)",
                "sarvam-m": "Sarvam-M (Lightweight)"
            }[x],
            help="105B is most capable but slower. 30B is faster, good for simple queries."
        )
        
        if model_choice != config.SARVAM_LLM_MODEL:
            config.SARVAM_LLM_MODEL = model_choice
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 🌐 Language")
        user_language = st.selectbox(
            "Your preferred language",
            options=list(config.LANGUAGES.keys()),
            format_func=lambda x: config.LANGUAGES[x]
        )
        
        st.markdown("---")
        st.markdown("### 📊 Complexity")
        complexity = st.select_slider(
            "Response detail level",
            options=["simple", "medium", "complex"],
            value="simple"
        )
        
        st.markdown("---")
        st.markdown("### 📈 Stats")
        st.metric("Conversations", len(st.session_state.conversations))
        st.metric("Total Queries", st.session_state.total_queries)
        
        st.markdown("---")
        st.markdown("### 🧠 About Current Model")
        if config.SARVAM_LLM_MODEL == "sarvam-105b":
            st.info("""
            **Sarvam-105B** is India's largest multilingual LLM:
            - 105 billion parameters
            - Trained on 22 Indian languages
            - Native script support
            - Best for complex reasoning
            - Available with standard API key
            """)
        elif config.SARVAM_LLM_MODEL == "sarvam-30b":
            st.info("""
            **Sarvam-30B** - Fast and capable:
            - 30 billion parameters
            - Faster response times
            - Great for everyday queries
            - Available with standard API key
            """)
        else:
            st.info("""
            **Sarvam-M** - Lightweight model:
            - Optimized for speed
            - Lower latency
            - Good for simple tasks
            """)
    
    if not api_key:
        st.warning("⚠️ Please enter your Sarvam API key in the sidebar.")
        st.stop()
    
    # Initialize clients
    sarvam = Sarvam105BClient(api_key)
    stt = SaarasClient(api_key)
    tts = BulbulClient(api_key)
    
    # Domain selection
    st.markdown("## 🎯 Choose a Domain")
    cols = st.columns(len(config.DOMAINS))
    for col, (domain_key, domain_data) in zip(cols, config.DOMAINS.items()):
        with col:
            if st.button(f"{domain_data['icon']}\n{domain_data['name']}", use_container_width=True):
                st.session_state.current_domain = domain_key
    
    current_domain = st.session_state.current_domain
    domain_data = config.DOMAINS[current_domain]
    st.info(f"**{domain_data['icon']} {domain_data['name']}** — {domain_data['description']}")
    
    st.markdown("---")
    
    # Input section
    st.markdown("## 🎤 Ask Your Question")
    col1, col2 = st.columns(2)
    
    query_text = ""
    
    with col1:
        st.markdown("**Type your question**")
        query_text = st.text_area("", height=120, 
                                  placeholder="Example: How do I grow wheat in rainy season? / गेहूं कैसे उगाएं?")
    
    with col2:
        st.markdown("**Or speak (max 30 seconds)**")
        audio_input = st.audio_input("Record your question")
        if audio_input:
            audio_bytes = audio_input.read()
            st.audio(audio_bytes, format="audio/wav")
            with st.spinner("🎙️ Transcribing with Saaras v3..."):
                try:
                    transcribed, detected = stt.transcribe(audio_bytes, "audio.wav", mode="translate")
                    query_text = transcribed
                    st.success(f"🗣️ You said: {transcribed[:150]}...")
                    st.caption(f"Detected language: {detected}")
                except Exception as e:
                    st.error(f"Transcription failed: {e}")
    
    # Process query
    if query_text and query_text.strip():
        st.markdown("---")
        
        with st.spinner(f"🧠 {get_model_display_name()} is thinking... (may take a few seconds)"):
            try:
                lang_name = config.LANGUAGES.get(user_language, "Hindi")
                
                # Progress indicators
                progress_bar = st.progress(0)
                progress_bar.progress(25, text="Analyzing your question...")
                
                # Understand intent (shows model capability)
                intent = sarvam.understand_intent(query_text, lang_name)
                progress_bar.progress(50, text="Generating response...")
                
                # Generate response
                response = sarvam.generate_response(
                    user_query=query_text,
                    domain=current_domain,
                    user_language=user_language,
                    lang_name=lang_name,
                    complexity_level=complexity,
                    conversation_history=st.session_state.conversations[-5:]
                )
                progress_bar.progress(75, text="Converting to speech...")
                
                # Generate voice
                audio_response = None
                try:
                    audio_response = tts.speak(response, user_language)
                except Exception as e:
                    st.warning(f"Voice generation skipped: {e}")
                
                progress_bar.progress(100, text="Complete!")
                time.sleep(0.5)
                progress_bar.empty()
                
                # Display response
                st.markdown(f"## 💬 Response from {get_model_display_name()}")
                st.markdown(f'<div class="response-card">{response}</div>', unsafe_allow_html=True)
                
                if audio_response:
                    st.audio(audio_response, format="audio/wav", autoplay=True)
                    st.caption("🔊 Voice response ready")
                
                # Show intent analysis
                with st.expander("🔍 How the model understood your query"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Detected Intent**")
                        st.json(intent)
                    with col_b:
                        st.markdown("**Response Stats**")
                        st.markdown(f"- Model: {get_model_display_name()}")
                        st.markdown(f"- Response length: {len(response)} characters")
                        st.markdown(f"- Language: {lang_name}")
                        st.markdown(f"- Complexity: {complexity}")
                
                # Save to history
                st.session_state.conversations.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "domain": current_domain,
                    "query": query_text,
                    "response": response
                })
                st.session_state.total_queries += 1
                st.session_state.total_chars += len(response)
                
                # Download buttons
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📝 Download Response",
                        response,
                        file_name=f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    )
                if audio_response:
                    with col2:
                        st.download_button(
                            "🔊 Download Audio Response",
                            audio_response,
                            file_name="voice_response.wav",
                            mime="audio/wav"
                        )
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.info("💡 Tips: Try a simpler question, check your API key, or select a different model in sidebar.")
    
    # Conversation history
    if st.session_state.conversations:
        st.markdown("---")
        st.markdown("## 📜 Recent Conversations")
        for conv in reversed(st.session_state.conversations[-5:]):
            with st.expander(f"{conv['timestamp']} - {conv['domain']}"):
                st.markdown(f"**You:** {conv['query'][:200]}")
                st.markdown(f"**Assistant:** {conv['response'][:300]}...")
    
    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style="text-align: center; color: #666; padding: 2rem;">
        <p>🇮🇳 <strong>Bharat Vaani</strong> — Breaking Language Barriers with Sarvam AI</p>
        <p>Models: <strong>{get_model_display_name()}</strong> + Saaras v3 (STT) + Bulbul v2 (TTS)</p>
        <p>Made in India • 22 Languages • Voice-First</p>
        <p style="font-size: 0.8rem; margin-top: 1rem;">
        You can switch between sarvam-105b, sarvam-30b, and sarvam-m in the sidebar
        </p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()