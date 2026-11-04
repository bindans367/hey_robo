# PROJECT AUDIT & SYSTEM ARCHITECTURE
## SIT Tumakuru Humanoid Campus Assistant (Robo)

---

## 1. System Overview

Robo is a hybrid voice-interactive and web-controlled conversational assistant deployed on a humanoid robot at **Siddaganga Institute of Technology (SIT), Tumakuru**. The system supports:
- **100% Offline operation**: Local Speech-to-Text (Whisper / Vosk), fuzzy-matcher retrieval against curated SIT data (`knowledge.json`, scraped pages, and department profiles), and Windows SAPI TTS.
- **Local AI generation**: On-device Ollama model (e.g. `qwen3:0.6b`).
- **Cloud AI generation**: Google Gemini API via OpenAI-compatible endpoints with local knowledge grounding.
- **Operator & Visual Display Plane**: Local web dashboard (`http://127.0.0.1:8765`) and real-time animated robotic eye display (`/eyes`).

---

## 2. Complete Architecture Map

```mermaid
flowchart TD
    subgraph UI_Layer["Frontend & UI Controls"]
        WebDashboard["web/index.html & app.js<br/>(Dashboard at :8765)"]
        EyeDisplay["web/eyes.html & eyes.js<br/>(Animated Eyes at :8765/eyes)"]
        ExternalEyes["eye-site/<br/>(Standalone Deployment)"]
        ConsoleUI["robot_ui.py<br/>(ASCII Robot Face / Terminal)"]
    end

    subgraph Audio_Layer["Audio & Speech Recognition (STT)"]
        MicInput["Microphone Input<br/>(mic_config.py)"] --> VE["voice_engine.py"]
        VE --> WModel["Faster-Whisper (Local tiny.en / cached)"]
        VE -. "Fallback" .-> VModel["Vosk Model (vosk-model-small-en-us-0.15)"]
        WModel --> STTText["Transcribed Utterance"]
        VModel --> STTText
    end

    subgraph Server_Core["Backend Orchestration & Routing"]
        Server["robo_brain.py<br/>(HTTP Server at 127.0.0.1:8765)"]
        Core["robo_brain_core.py<br/>(Settings, Answering Engine, History)"]
        Normalizer["normalizer.py<br/>(Phonetic & regional Indian accent aliases)"]
        MatcherEngine["matcher.py<br/>(RapidFuzz token_set/partial matching)"]
    end

    subgraph Data_Storage["Knowledge & State Stores"]
        KB[("knowledge.json<br/>(Curated QA)")]
        Depts[("data/sit_departments.json<br/>(Profiles & Labs)")]
        WebPages[("data/sit_website_pages.json<br/>(Scraped pages)")]
        Settings[("data/robo_settings.json")]
        RuntimeState[("data/robo_runtime_state.json")]
        History[("data/robo_history.json")]
    end

    subgraph AI_Engines["Intelligence Providers"]
        MatcherEngine --> KB
        MatcherEngine --> Depts
        MatcherEngine --> WebPages

        Core --> ModeRouter{Mode Selector}
        ModeRouter -->|"offline"| MatcherEngine
        ModeRouter -->|"local"| Ollama["Local Ollama<br/>(qwen3:0.6b at :11434)"]
        ModeRouter -->|"online"| Gemini["Google Gemini API<br/>(gemini-3.5-flash-lite via HTTPS)"]
    end

    subgraph Speech_Output["Speech Synthesis (TTS)"]
        TTSSelect{TTS Engine}
        TTSSelect -->|"Offline"| SAPI["Windows SAPI TTS"]
        TTSSelect -->|"Online Neural"| EdgeTTS["Microsoft Edge TTS (en-IN voices)"]
        SAPI --> Speaker["Speaker Output"]
        EdgeTTS --> Speaker
    end

    %% Wiring
    WebDashboard <-->|REST API /api/*| Server
    EyeDisplay <-->|Polling /api/status| Server
    ExternalEyes <-->|Polling /api/status| Server
    Server <--> Core
    STTText --> Normalizer --> Core
    Core --> TTSSelect
    Core --> RuntimeState
    Core --> Settings
    Core --> History
```

---

## 3. Communication Pathways & Data Flow

1. **Voice Input Flow**:
   - `bot.py` reads microphone stream via `voice_engine.listen()`.
   - `voice_engine.py` attempts decoding with Faster-Whisper; falls back to chunked Vosk Kaldi recognizer if Whisper fails.
   - Decoded string is normalized in `normalizer.py` (e.g., correcting acoustic aliases like *"bella auditor young"* $\rightarrow$ *"Birla Auditorium"*).
   - `robo_brain_core.py` routes the normalized query according to the selected mode (`offline`, `local`, or `online`).

2. **Knowledge Retrieval Flow**:
   - In `offline` mode, `matcher.py` searches `knowledge.json`, `sit_departments.json`, and `sit_website_pages.json` using RapidFuzz ratio metrics.
   - In `local` or `online` mode, the matched local SIT answer is injected as grounding context into the prompt sent to the LLM.

3. **Status & Eye Synchronization**:
   - `bot.py` calls `core.publish_runtime(phase, ...)`, which writes to `data/robo_runtime_state.json`.
   - The web dashboard (`app.js`) and animated eye panel (`eyes.js`) poll `/api/status` to synchronize eye movements, states (`sleeping`, `listening`, `thinking`, `speaking`), and live transcript feeds.
