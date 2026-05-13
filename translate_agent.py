from __future__ import annotations

import base64
import html
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
import requests


SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
MAX_CHARS_PER_REQUEST = 1900
MAX_MAYURA_CHARS_PER_REQUEST = 900
MAX_TTS_CHARS = 2400
MAX_TTS_CHARS_V2 = 1400
MAX_QA_CONTEXT_CHARS = 24000

SUPPORTED_LANGUAGES = {
    "as-IN": "Assamese",
    "bn-IN": "Bengali",
    "brx-IN": "Bodo",
    "doi-IN": "Dogri",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "kok-IN": "Konkani",
    "ks-IN": "Kashmiri",
    "mai-IN": "Maithili",
    "ml-IN": "Malayalam",
    "mni-IN": "Manipuri",
    "mr-IN": "Marathi",
    "ne-IN": "Nepali",
    "od-IN": "Odia",
    "pa-IN": "Punjabi",
    "sa-IN": "Sanskrit",
    "sat-IN": "Santali",
    "sd-IN": "Sindhi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "ur-IN": "Urdu",
}

TTS_LANGUAGES = {
    "bn-IN",
    "en-IN",
    "gu-IN",
    "hi-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "od-IN",
    "pa-IN",
    "ta-IN",
    "te-IN",
}


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


class SarvamTranslateAgent:
    def __init__(
        self,
        api_key: str,
        source_language_code: str,
        target_language_code: str,
        model: str = "sarvam-translate:v1",
        numerals_format: str = "international",
        enable_preprocessing: bool = True,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key
        self.source_language_code = source_language_code
        self.target_language_code = target_language_code
        self.model = model
        self.numerals_format = numerals_format
        self.enable_preprocessing = enable_preprocessing
        self.timeout_seconds = timeout_seconds

    def translate_pdf(self, input_pdf: Path, output_pdf: Path, output_txt: Path) -> None:
        pages = extract_pdf_text(input_pdf)
        if not any(page.text.strip() for page in pages):
            raise ValueError(
                "No selectable text found in the PDF. Run OCR first, then translate the OCR output."
            )

        translated_pages: list[PdfPageText] = []
        for page in pages:
            print(f"Translating page {page.page_number}/{len(pages)}...")
            translated_text = self.translate_text(page.text) if page.text.strip() else ""
            translated_pages.append(PdfPageText(page.page_number, translated_text))

        write_translated_text(translated_pages, output_txt)
        write_translated_pdf(translated_pages, output_pdf, title=f"Translated to {self.target_language_code}")

    def translate_text(self, text: str) -> str:
        chunks = split_text(text, MAX_CHARS_PER_REQUEST)
        translated_chunks = [self._translate_chunk(chunk) for chunk in chunks if chunk.strip()]
        return "\n\n".join(translated_chunks)

    def _translate_chunk(self, chunk: str) -> str:
        payload = {
            "input": chunk,
            "source_language_code": self.source_language_code,
            "target_language_code": self.target_language_code,
            "model": self.model,
            "mode": "formal",
            "numerals_format": self.numerals_format,
            "enable_preprocessing": self.enable_preprocessing,
        }
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        for attempt in range(1, 4):
            response = requests.post(
                SARVAM_TRANSLATE_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 and attempt < 3:
                time.sleep(2 * attempt)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                detail = response.text.strip()
                raise RuntimeError(f"Sarvam translation failed: {response.status_code} {detail}") from exc

            data = response.json()
            translated = data.get("translated_text")
            if not translated:
                raise RuntimeError(f"Sarvam response did not include translated_text: {data}")
            return translated

        raise RuntimeError("Sarvam translation was rate-limited after multiple retries.")


def synthesize_speech(
    api_key: str,
    text: str,
    target_language_code: str,
    model: str = "bulbul:v2",
    speaker: str = "shubh",
    pace: float = 1.0,
) -> bytes:
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("No translated text available to speak.")
    if target_language_code not in TTS_LANGUAGES:
        raise ValueError(f"Text-to-speech is not available for {target_language_code}.")

    max_chars = MAX_TTS_CHARS_V2 if model == "bulbul:v2" else MAX_TTS_CHARS
    payload = {
        "text": clean_text[:max_chars],
        "target_language_code": target_language_code,
        "model": model,
        "speaker": speaker,
        "pace": pace,
        "speech_sample_rate": 24000,
    }
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    response = requests.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=60)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        raise RuntimeError(f"Sarvam text-to-speech failed: {response.status_code} {detail}") from exc

    data = response.json()
    audios = data.get("audios") or []
    if not audios:
        raise RuntimeError(f"Sarvam response did not include audio: {data}")
    return base64.b64decode(audios[0])


def transcribe_audio(
    api_key: str,
    audio_bytes: bytes,
    filename: str,
    language_code: str = "unknown",
) -> str:
    headers = {"api-subscription-key": api_key}
    content_type = mimetypes.guess_type(filename)[0] or "audio/wav"
    files = {"file": (filename, audio_bytes, content_type)}
    data = {
        "model": "saaras:v3",
        "mode": "transcribe",
        "language_code": language_code,
    }
    response = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data, timeout=90)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        raise RuntimeError(f"Sarvam speech-to-text failed: {response.status_code} {detail}") from exc

    transcript = response.json().get("transcript")
    if not transcript:
        raise RuntimeError(f"Sarvam response did not include transcript: {response.text}")
    return transcript


def translate_text_to_language(
    api_key: str,
    text: str,
    target_language_code: str,
    source_language_code: str = "auto",
) -> str:
    if target_language_code == "en-IN" and source_language_code == "en-IN":
        return text

    agent = SarvamTranslateAgent(
        api_key=api_key,
        source_language_code=source_language_code,
        target_language_code=target_language_code,
        model="mayura:v1",
    )
    chunks = split_text(text, MAX_MAYURA_CHARS_PER_REQUEST)
    return "\n\n".join(agent._translate_chunk(chunk) for chunk in chunks if chunk.strip())


def answer_question_from_document(
    api_key: str,
    document_text: str,
    question: str,
    answer_language_code: str,
    model: str = "sarvam-30b",
) -> str:
    context = document_text[:MAX_QA_CONTEXT_CHARS]
    language_name = SUPPORTED_LANGUAGES.get(answer_language_code, answer_language_code)
    messages = [
        {
            "role": "system",
            "content": (
                "You answer questions using only the provided translated document. "
                "If the answer is not present, say that it is not found in the document. "
                f"Answer only in {language_name}. Do not answer in English unless the target language is English."
            ),
        },
        {
            "role": "user",
            "content": f"Translated document:\n{context}\n\nQuestion:\n{question}",
        },
    ]
    headers = {
        "api-subscription-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 500,
    }
    response = requests.post(SARVAM_CHAT_URL, headers=headers, json=payload, timeout=90)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        raise RuntimeError(f"Sarvam Q&A failed: {response.status_code} {detail}") from exc

    data = response.json()
    answer = extract_chat_answer(data)
    if answer:
        return answer

    if model != "sarvam-m":
        return answer_question_from_document(
            api_key,
            document_text,
            question,
            answer_language_code,
            model="sarvam-m",
        )

    raise RuntimeError(f"Sarvam response did not include a text answer: {data}")


def extract_chat_answer(data: dict) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content.strip()

    return None


def extract_pdf_text(input_pdf: Path) -> list[PdfPageText]:
    document = fitz.open(input_pdf)
    try:
        return [
            PdfPageText(page_number=index + 1, text=page.get_text("text").strip())
            for index, page in enumerate(document)
        ]
    finally:
        document.close()


def split_text(text: str, max_chars: int) -> list[str]:
    normalized = re.sub(r"[ \t]+\n", "\n", text).strip()
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in re.split(r"\n\s*\n", normalized):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) > max_chars:
            flush_chunk(current, chunks)
            current = []
            current_len = 0
            chunks.extend(split_long_paragraph(paragraph, max_chars))
            continue

        projected_len = current_len + len(paragraph) + 2
        if current and projected_len > max_chars:
            flush_chunk(current, chunks)
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = projected_len

    flush_chunk(current, chunks)
    return chunks


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?\u0964])\s+", paragraph)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars))
            continue

        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()

    if current:
        chunks.append(current.strip())
    return chunks


def flush_chunk(current: list[str], chunks: list[str]) -> None:
    if current:
        chunks.append("\n\n".join(current).strip())


def write_translated_text(pages: Iterable[PdfPageText], output_txt: Path) -> None:
    content = []
    for page in pages:
        content.append(f"--- Page {page.page_number} ---\n{page.text}\n")
    output_txt.write_text("\n".join(content), encoding="utf-8")


def write_translated_pdf(pages: Iterable[PdfPageText], output_pdf: Path, title: str) -> None:
    document = fitz.open()
    css = """
    body {
      font-family: sans-serif;
      font-size: 12pt;
      line-height: 1.45;
    }
    h1 {
      font-size: 13pt;
      margin: 0 0 12pt 0;
    }
    p {
      margin: 0 0 9pt 0;
      white-space: pre-wrap;
    }
    """

    for page_text in pages:
        pdf_page_parts = split_text(page_text.text, 2200) if page_text.text.strip() else [""]
        total_parts = len(pdf_page_parts)

        for part_index, page_part in enumerate(pdf_page_parts, start=1):
            source_label = f"Page {page_text.page_number}"
            if total_parts > 1:
                source_label = f"{source_label}.{part_index}"

            add_pdf_page(document, title, source_label, page_part, css)

    document.save(output_pdf)
    document.close()


def add_pdf_page(document: fitz.Document, title: str, source_label: str, text: str, css: str) -> None:
    page = document.new_page(width=595, height=842)
    rect = fitz.Rect(54, 54, 541, 788)
    body = paragraphs_to_html(text)
    page_html = f"<h1>{html.escape(title)} - {html.escape(source_label)}</h1>{body}"
    try:
        page.insert_htmlbox(rect, page_html, css=css)
    except Exception:
        page.insert_textbox(
            rect,
            f"{title} - {source_label}\n\n{text}",
            fontsize=11,
            fontname="helv",
            align=fitz.TEXT_ALIGN_LEFT,
        )


def paragraphs_to_html(text: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return "<p></p>"
    return "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
