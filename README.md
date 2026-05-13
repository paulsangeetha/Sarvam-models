# Sarvam PDF Translator

Simple Streamlit app to translate a text-based PDF into an Indian language using Sarvam.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the app:

```powershell
streamlit run app.py
```

You can paste your Sarvam key into the app, or set it first:

```powershell
$env:SARVAM_API_KEY="your_sarvam_api_subscription_key"
```

## Supported Languages

| Code | Language |
| --- | --- |
| `hi-IN` | Hindi |
| `ta-IN` | Tamil |
| `te-IN` | Telugu |
| `kn-IN` | Kannada |
| `ml-IN` | Malayalam |
| `mr-IN` | Marathi |
| `bn-IN` | Bengali |
| `gu-IN` | Gujarati |
| `pa-IN` | Punjabi |
| `od-IN` | Odia |
| `en-IN` | English |

## Notes

- The app uses Sarvam's `/translate` API.
- Each request is chunked under Sarvam's text limit.
- Scanned PDFs need OCR first; this agent translates selectable PDF text.
