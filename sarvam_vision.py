"""
===============================================================================
SARVAM VISION - Document Intelligence Dashboard
===============================================================================
"""

import streamlit as st
import zipfile
import os
import tempfile
from datetime import datetime
from sarvamai import SarvamAI

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Sarvam Vision - Document Intelligence",
    page_icon="🔍",
    layout="wide"
)

# ============================================================================
# LANGUAGE MAPPING
# ============================================================================

LANGUAGES = {
    "en-IN": "English",
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
    "ur-IN": "اُردُو (Urdu)"
}

# ============================================================================
# HEADER
# ============================================================================

st.title("🔍 Sarvam Vision - Document Intelligence")
st.markdown("""
Extract text from **PDFs, images, and handwritten documents** in **Indian languages**.
Powered by Sarvam Vision 3B Model.
""")

# ============================================================================
# SIDEBAR - API KEY
# ============================================================================

with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    
    api_key = st.text_input(
        "Sarvam API Key",
        type="password",
        placeholder="Enter your API key here",
        help="Get your key from platform.sarvam.ai"
    )
    
    st.markdown("---")
    st.markdown("### 📋 Instructions")
    st.markdown("""
    1. Enter your API key above
    2. Upload a PDF or image
    3. Select document language
    4. Click **Process Document**
    5. Download extracted text
    """)
    
    st.markdown("---")
    st.markdown("### 💰 Pricing")
    st.markdown("₹1.5 per page")
    
    st.markdown("---")
    st.markdown("### 📞 Need Help?")
    st.markdown("Email: **support@sarvam.ai**")

# ============================================================================
# MAIN CONTENT
# ============================================================================

if not api_key:
    st.warning("👈 Please enter your Sarvam API key in the sidebar")
    st.stop()

# Document upload section
st.markdown("## 📄 Upload Document")

col1, col2 = st.columns([1, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "jpg", "jpeg", "png"],
        help="PDF, JPG, or PNG files (max 10 pages)",
        label_visibility="collapsed"
    )

with col2:
    language = st.selectbox(
        "Document Language",
        options=list(LANGUAGES.keys()),
        format_func=lambda x: LANGUAGES[x],
        help="Select the language of your document"
    )
    
    output_format = st.radio(
        "Output Format",
        options=["md", "html"],
        format_func=lambda x: "Markdown (.md)" if x == "md" else "HTML (.html)",
        horizontal=True
    )

# Show file preview
if uploaded_file:
    if uploaded_file.type.startswith('image/'):
        st.image(uploaded_file, width=300, caption="Uploaded document")
    
    st.info(f"📎 **File:** {uploaded_file.name} | **Size:** {uploaded_file.size/1024:.1f} KB")

# ============================================================================
# PROCESS BUTTON
# ============================================================================

if st.button("🚀 Process Document", type="primary", use_container_width=True):
    
    if not uploaded_file:
        st.error("Please upload a file first")
        st.stop()
    
    # Progress indicators
    progress_bar = st.progress(0)
    status_text = st.empty()
    result_container = st.container()
    
    try:
        # Step 1: Initialize client
        status_text.info("🔑 Initializing Sarvam client...")
        progress_bar.progress(10)
        
        client = SarvamAI(api_subscription_key=api_key)
        
        # Step 2: Create job
        status_text.info("📝 Creating document intelligence job...")
        progress_bar.progress(20)
        
        job = client.document_intelligence.create_job(
            language=language,
            output_format=output_format
        )
        
        # Step 3: Save uploaded file to temp file
        status_text.info("💾 Saving uploaded file...")
        progress_bar.progress(30)
        
        with tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=f".{uploaded_file.name.split('.')[-1]}"
        ) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        # Step 4: Upload file
        status_text.info("📤 Uploading file to Sarvam...")
        progress_bar.progress(40)
        
        job.upload_file(tmp_path)
        
        # Step 5: Start processing
        status_text.info("🚀 Starting document processing...")
        progress_bar.progress(50)
        
        job.start()
        
        # Step 6: Wait for completion
        status_text.info("⏳ Processing document (10-30 seconds)...")
        progress_bar.progress(60)
        
        status = job.wait_until_complete()
        
        # Step 7: Get metrics
        progress_bar.progress(80)
        metrics = job.get_page_metrics()
        
        status_text.info("📥 Downloading results...")
        progress_bar.progress(90)
        
        # Step 8: Download output
        output_zip = f"vision_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        job.download_output(output_zip)
        
        progress_bar.progress(100)
        status_text.empty()
        
        # Step 9: Extract text from ZIP
        extracted_text = ""
        html_content = ""
        
        with zipfile.ZipFile(output_zip, 'r') as zf:
            for file_name in zf.namelist():
                with zf.open(file_name) as f:
                    content = f.read().decode('utf-8')
                    if file_name.endswith('.md'):
                        extracted_text = content
                    elif file_name.endswith('.html'):
                        html_content = content
        
        # ================================================================
        # DISPLAY RESULTS
        # ================================================================
        
        with result_container:
            st.markdown("---")
            st.markdown("## ✅ Processing Complete!")
            
            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Status", status.job_state)
            with col2:
                st.metric("Pages Processed", metrics.get("pages_processed", 1))
            with col3:
                st.metric("Output Format", output_format.upper())
            with col4:
                st.metric("Language", LANGUAGES.get(language, language))
            
            # Show extracted text
            if extracted_text or html_content:
                st.markdown("### 📄 Extracted Content")
                
                if output_format == "md":
                    st.markdown(extracted_text[:5000])
                else:
                    st.components.v1.html(html_content[:5000], height=400)
                
                # Download buttons
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        "📥 Download as Text",
                        extracted_text if extracted_text else html_content,
                        file_name=f"extracted_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{output_format}",
                        mime="text/plain"
                    )
                
                with col2:
                    with open(output_zip, "rb") as f:
                        st.download_button(
                            "📦 Download Full ZIP",
                            f.read(),
                            file_name=output_zip,
                            mime="application/zip"
                        )
            else:
                st.warning("No text was extracted. Check the ZIP file for results.")
                with open(output_zip, "rb") as f:
                    st.download_button(
                        "📦 Download Output ZIP",
                        f.read(),
                        file_name=output_zip,
                        mime="application/zip"
                    )
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
    except Exception as e:
        st.error(f"❌ Processing failed: {str(e)}")
        
        # Helpful error messages
        error_msg = str(e).lower()
        if "403" in error_msg or "forbidden" in error_msg:
            st.info("""
            🔑 **Permission Error:** Your API key doesn't have Document Intelligence access.
            
            Please email **support@sarvam.ai** to request access.
            Include your API key prefix in the email.
            """)
        elif "404" in error_msg or "not found" in error_msg:
            st.info("""
            📁 **Endpoint Error:** Document Intelligence is not available for your account.
            
            Contact **support@sarvam.ai** to enable this feature.
            """)
        elif "422" in error_msg or "unprocessable" in error_msg:
            st.info("""
            💡 **File Error:** Please check:
            - File size must be under 200 MB
            - Maximum 10 pages per document
            - PDF must be valid and readable
            - For images: JPG or PNG format
            """)
        elif "timeout" in error_msg:
            st.info("⏱️ **Timeout:** The document took too long to process. Try a smaller file.")
        else:
            st.info(f"💡 **Error Details:** {e}")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <p>🇮🇳 <strong>Sarvam Vision</strong> — Document Intelligence for 22 Indian Languages</p>
    <p style="font-size: 0.8rem;">Powered by Sarvam AI | Made in India</p>
</div>
""", unsafe_allow_html=True)