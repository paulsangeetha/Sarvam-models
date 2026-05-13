from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from translate_agent import (
    MAX_TTS_CHARS,
    MAX_TTS_CHARS_V2,
    SUPPORTED_LANGUAGES,
    TTS_LANGUAGES,
    SarvamTranslateAgent,
    answer_question_from_document,
    synthesize_speech,
    transcribe_audio,
    translate_text_to_language,
)


st.set_page_config(page_title="Sarvam PDF Translator", layout="centered")

st.title("Sarvam PDF Translator")
st.write("Upload a text-based PDF and translate it into an Indian language.")

api_key = st.text_input(
    "Sarvam API key",
    value=os.getenv("SARVAM_API_KEY", ""),
    type="password",
    help="You can also set SARVAM_API_KEY in your environment.",
)

uploaded_pdf = st.file_uploader("PDF", type=["pdf"])

language_options = {f"{name} ({code})": code for code, name in sorted(SUPPORTED_LANGUAGES.items())}
target_label = st.selectbox("Translate to", list(language_options.keys()), index=list(language_options.values()).index("hi-IN"))
source_codes = sorted(SUPPORTED_LANGUAGES)
source_code = st.selectbox("Source language", source_codes, index=source_codes.index("en-IN"))

native_numerals = st.checkbox("Use native numerals")

translate_tab, listen_tab, qa_tab = st.tabs(["Translate", "Listen", "Q&A"])

with translate_tab:
    if st.button("Translate", type="primary", disabled=not uploaded_pdf or not api_key):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / uploaded_pdf.name
            output_pdf = temp_path / f"{input_pdf.stem}.{language_options[target_label]}.pdf"
            output_txt = temp_path / f"{input_pdf.stem}.{language_options[target_label]}.txt"
            input_pdf.write_bytes(uploaded_pdf.getbuffer())

            agent = SarvamTranslateAgent(
                api_key=api_key,
                source_language_code=source_code,
                target_language_code=language_options[target_label],
                numerals_format="native" if native_numerals else "international",
            )

            try:
                with st.spinner("Translating PDF with Sarvam..."):
                    agent.translate_pdf(input_pdf, output_pdf, output_txt)
            except Exception as exc:
                st.error(f"Translation failed: {exc}")
            else:
                st.session_state["translated_pdf"] = output_pdf.read_bytes()
                st.session_state["translated_txt"] = output_txt.read_bytes()
                st.session_state["translated_text"] = output_txt.read_text(encoding="utf-8")
                st.session_state["translated_pdf_name"] = output_pdf.name
                st.session_state["translated_txt_name"] = output_txt.name
                st.session_state["target_language_code"] = language_options[target_label]
                st.success("Translation complete")

    if "translated_pdf" in st.session_state:
        st.download_button(
            "Download translated PDF",
            data=st.session_state["translated_pdf"],
            file_name=st.session_state["translated_pdf_name"],
            mime="application/pdf",
        )
        st.download_button(
            "Download translated text",
            data=st.session_state["translated_txt"],
            file_name=st.session_state["translated_txt_name"],
            mime="text/plain",
        )

with listen_tab:
    translated_text = st.session_state.get("translated_text", "")
    target_code = st.session_state.get("target_language_code", language_options[target_label])

    if not translated_text:
        st.info("Translate a PDF first, then come here to listen.")
    elif target_code not in TTS_LANGUAGES:
        st.warning(f"Listening is not available for {target_code}. Choose one of Sarvam's TTS languages.")
    else:
        tts_model = st.selectbox("Speech model", ["bulbul:v2", "bulbul:v3"])
        speakers = ["anushka", "abhilash", "vidya", "manisha", "arya", "karun", "hitesh"]
        if tts_model == "bulbul:v3":
            speakers = ["shubh", "anushka", "abhilash", "vidya", "manisha", "arya", "karun", "hitesh"]
        speaker = st.selectbox("Voice", speakers)
        pace = st.slider("Pace", min_value=0.5, max_value=2.0, value=1.0, step=0.1)
        max_tts_chars = MAX_TTS_CHARS_V2 if tts_model == "bulbul:v2" else MAX_TTS_CHARS
        preview_text = translated_text[:max_tts_chars]
        st.text_area("Text to speak", preview_text, height=180, disabled=True)

        if len(translated_text) > max_tts_chars:
            st.caption("Long translations are spoken as a preview from the beginning.")

        if st.button("Generate audio", disabled=not api_key):
            try:
                with st.spinner("Generating audio with Sarvam..."):
                    audio_bytes = synthesize_speech(
                        api_key,
                        preview_text,
                        target_code,
                        model=tts_model,
                        speaker=speaker,
                        pace=pace,
                    )
            except Exception as exc:
                st.error(f"Audio generation failed: {exc}")
            else:
                st.audio(audio_bytes, format="audio/wav")
                st.download_button("Download audio", audio_bytes, file_name="translation.wav", mime="audio/wav")

with qa_tab:
    translated_text = st.session_state.get("translated_text", "")
    target_code = st.session_state.get("target_language_code", language_options[target_label])

    if not translated_text:
        st.info("Translate a PDF first, then ask questions from the translated document.")
    else:
        st.write(
            f"Ask a question by voice. The answer will use only the translated document and play in {target_code}."
        )
        question_audio = st.audio_input("Question audio")
        uploaded_question_audio = st.file_uploader(
            "Or upload question audio",
            type=["wav", "mp3", "m4a", "aac", "ogg", "opus", "flac", "webm"],
            key="qa_audio_upload",
        )
        qa_tts_model = st.selectbox("Answer speech model", ["bulbul:v2", "bulbul:v3"], key="qa_tts_model")
        qa_speakers = ["anushka", "abhilash", "vidya", "manisha", "arya", "karun", "hitesh"]
        if qa_tts_model == "bulbul:v3":
            qa_speakers = ["shubh", *qa_speakers]
        qa_speaker = st.selectbox("Answer voice", qa_speakers, key="qa_speaker")

        audio_file = question_audio or uploaded_question_audio
        if st.button("Ask", type="primary", disabled=not audio_file or not api_key):
            audio_bytes = audio_file.getvalue()
            filename = getattr(audio_file, "name", "question.wav")
            if "." not in filename:
                filename = "question.wav"
            try:
                with st.spinner("Listening to your question..."):
                    question_text = transcribe_audio(api_key, audio_bytes, filename, language_code="unknown")
                with st.spinner("Finding the answer in the translated document..."):
                    answer_text = answer_question_from_document(api_key, translated_text, question_text, target_code)
                    if target_code != "en-IN":
                        answer_text = translate_text_to_language(api_key, answer_text, target_code)

                st.session_state["qa_question"] = question_text
                st.session_state["qa_answer"] = answer_text

                if target_code in TTS_LANGUAGES:
                    with st.spinner("Speaking the answer..."):
                        st.session_state["qa_answer_audio"] = synthesize_speech(
                            api_key,
                            answer_text,
                            target_code,
                            model=qa_tts_model,
                            speaker=qa_speaker,
                        )
                else:
                    st.session_state.pop("qa_answer_audio", None)
            except Exception as exc:
                st.error(f"Q&A failed: {exc}")

        if "qa_question" in st.session_state:
            st.text_area("Question", st.session_state["qa_question"], height=100, disabled=True)
        if "qa_answer" in st.session_state:
            st.text_area("Answer", st.session_state["qa_answer"], height=160, disabled=True)
        if "qa_answer_audio" in st.session_state:
            st.audio(st.session_state["qa_answer_audio"], format="audio/wav")
            st.download_button(
                "Download answer audio",
                st.session_state["qa_answer_audio"],
                file_name="answer.wav",
                mime="audio/wav",
            )
