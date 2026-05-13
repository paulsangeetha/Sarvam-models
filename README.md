# VoxBridge AI

VoxBridge AI is a premium multilingual voice assistant UI for hackathon demos and startup-style product pitches.

It records speech, transcribes with Sarvam Saaras v3 using `mode="transcribe"`, generates a short conversational response with Sarvam-30B or Sarvam-105B, and speaks back using Bulbul.

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── README.md
├── .env
└── app
    ├── main.py
    ├── assets
    ├── components
    ├── config
    ├── pages
    ├── styles
    └── utils
```

## Features

- Premium pastel glassmorphism UI
- Animated waveform hero and voice console
- Multilingual language and voice controls
- Saaras v3 transcription
- Sarvam-30B / Sarvam-105B response generation
- Optional Sarvam Wikipedia grounding for factual questions
- Bulbul v3 speech output
- Conversation memory with prompt-drift protection
- Polished status, transcript, playback, and response panels

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env`:

```env
SARVAM_API_KEY=your_sarvam_api_key_here
```

## Run

```bash
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Demo Prompts

- "I want smart home security for my front door and all windows."
- "My internet is not working since morning. Please help me fix it."
- "Please explain how I can book a doctor appointment."
- "Explain this bank SMS to me in simple Hindi."
- "Who is the current President of India?"

## Future Improvements

- Real-time streaming STT and partial transcripts
- FastAPI backend with user authentication
- CRM and smart home integrations
- Analytics dashboard for intent, language, and resolution rate
- Saved voice profiles and brand-specific assistant personas

## UI Optimization Ideas

- Add real waveform visualization from microphone amplitude
- Add brand themes for enterprise demos
- Add dark and light theme toggle
- Add animated route transitions if moved to a frontend framework

## Performance Suggestions

- Keep only a short rolling conversation window
- Queue long audio jobs in a worker for production
- Cache static configuration and theme assets
- Store audio only with user consent
