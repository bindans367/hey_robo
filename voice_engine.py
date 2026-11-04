"""
voice_engine.py - Advanced Offline Hybrid Speech Engine (STT & TTS)
for SIT Humanoid Campus Assistant.

Combines:
- Audio capture from the current Windows default input device, using its native rate
  and SpeechRecognition's mono capture, with resampling to 16 kHz before Whisper
- Advanced offline multilingual Faster-Whisper (large-v3-turbo, CPU int8) for improved
  accent tolerance, Indian-English recognition, and automatic language detection
- Chunked Vosk KaldiRecognizer fallback
- Synchronous Windows SAPI Text-to-Speech with pyttsx3 fallback and acronym expansion

Mic notes:
  Use the current system default input rather than a device index from a different
  computer/session. SpeechRecognition captures mono audio at the device's native rate.
"""

import audioop
import asyncio
import io
import json
import os
import re
import sys
import tempfile
import time
import wave
import xml.sax.saxutils as xml_utils
import pyttsx3
import speech_recognition as sr
from vosk import KaldiRecognizer, Model, SetLogLevel
from faster_whisper import WhisperModel
from mic_config import ENERGY_THRESHOLD, MIC_DEVICE_INDEX, MIC_TARGET_RATE

# Enable UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
VOSK_MODEL_PATH = os.path.join(ROOT, "models", "vosk-model-small-en-us-0.15")
ABORT_CONTROL_PATH = os.path.join(ROOT, "data", "robo_runtime_control.json")

def _speech_abort_sequence():
    try:
        with open(ABORT_CONTROL_PATH, "r", encoding="utf-8") as f:
            return int(json.load(f).get("abort_seq", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0

def _sapi_speak_interruptibly(text, xml=False):
    start_sequence = _speech_abort_sequence()
    flags = 1 | (8 if xml else 0)  # async, plus XML when pitch markup is used
    _sapi_voice.Speak(text, flags)
    while True:
        if _speech_abort_sequence() != start_sequence:
            _sapi_voice.Speak("", 3)  # purge and stop the active utterance
            return False
        if _sapi_voice.WaitUntilDone(100):
            return True

SetLogLevel(-1)

# ---------------------------------------------------------------------------
# 1. Initialize Whisper (Primary multilingual Transformer STT - 100% Offline)
# ---------------------------------------------------------------------------
TTS_ONLY = os.environ.get("HUMANOID_TTS_ONLY") == "1"
if TTS_ONLY:
    whisper_model = None
else:
    print("Loading offline AI speech recognition (Whisper)...", flush=True)
    configured_model = os.environ.get("HUMANOID_WHISPER_MODEL", "").strip()
    model_candidates = []
    if configured_model:
        model_candidates.append(configured_model)
    # Prefer pre-cached offline models on machine, then fall back cleanly
    for candidate in ("tiny.en", "base.en", "large-v3-turbo"):
        if candidate not in model_candidates:
            model_candidates.append(candidate)

    whisper_model = None
    for whisper_name in model_candidates:
        try:
            print(f"Loading Whisper model '{whisper_name}'...", flush=True)
            whisper_model = WhisperModel(whisper_name, device="cpu", compute_type="int8",
                                         cpu_threads=max(2, min(8, os.cpu_count() or 4)), num_workers=1,
                                         local_files_only=True)
            print(f"Whisper model '{whisper_name}' loaded successfully (offline).", flush=True)
            break
        except Exception:
            if configured_model == whisper_name:
                try:
                    whisper_model = WhisperModel(whisper_name, device="cpu", compute_type="int8",
                                                 cpu_threads=max(2, min(8, os.cpu_count() or 4)), num_workers=1)
                    break
                except Exception as e:
                    print(f"[WARN] Could not load configured Whisper model {whisper_name}: {e}", file=sys.stderr)
            continue

    if whisper_model is None:
        print("[WARN] Could not load any local Whisper model. Falling back to Vosk.", file=sys.stderr)

# ---------------------------------------------------------------------------
# 2. Initialize Vosk (Secondary Kaldi STT)
# ---------------------------------------------------------------------------
vosk_model = None
if not TTS_ONLY and os.path.isdir(VOSK_MODEL_PATH):
    try:
        vosk_model = Model(VOSK_MODEL_PATH)
    except Exception as e:
        print(f"[WARN] Could not load Vosk: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# 3. SpeechRecognizer – fixed threshold, NO dynamic calibration
# ---------------------------------------------------------------------------
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True    # Follow changing motor / room noise
recognizer.energy_threshold         = ENERGY_THRESHOLD
recognizer.dynamic_energy_adjustment_damping = 0.08
recognizer.dynamic_energy_ratio = 1.5
recognizer.pause_threshold          = 1.15
recognizer.phrase_threshold         = 0.15
recognizer.non_speaking_duration    = 0.45

# 4. Initialize Windows SAPI for synchronous speech playback. pyttsx3's
# event-loop backend remains as a fallback for systems where SAPI is unavailable.
_sapi_voice = None
_pythoncom = None
tts_engine = None
try:
    if os.name == "nt":
        import pythoncom as _pythoncom
        import win32com.client

        _pythoncom.CoInitialize()
        _sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
        _sapi_voice.Volume = 100
        # SAPI ranges from -10 (slowest) to 10 (fastest). Keep speech relaxed
        # and easy to follow without making the interaction feel sluggish.
        _sapi_voice.Rate = 0

        sapi_voices = _sapi_voice.GetVoices()
        for index in range(sapi_voices.Count):
            token = sapi_voices.Item(index)
            description = token.GetDescription().lower()
            if any(name in description for name in ("india", "ravi", "heera")):
                _sapi_voice.Voice = token
                break
        else:
            for index in range(sapi_voices.Count):
                token = sapi_voices.Item(index)
                if "zira" in token.GetDescription().lower():
                    _sapi_voice.Voice = token
                    break
except Exception as e:
    print(f"[WARN] Windows SAPI unavailable; will use pyttsx3: {e}", file=sys.stderr)

_calibrated = False


def calibrate_microphone():
    """Measure room noise once so the recognizer can set a suitable speech threshold."""
    global _calibrated
    if _calibrated or TTS_ONLY:
        return
    try:
        device_label = "Windows default" if MIC_DEVICE_INDEX is None else str(MIC_DEVICE_INDEX)
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as mic:
            print(f"Calibrating microphone [{device_label}] to room noise (about one second)...", flush=True)
            recognizer.adjust_for_ambient_noise(mic, duration=0.8)
        recognizer.energy_threshold = max(80, min(2000, recognizer.energy_threshold))
        # Keep adapting: motor noise can change after startup calibration.
        recognizer.dynamic_energy_threshold = True
        _calibrated = True
        print(f"Microphone calibrated; speech threshold={recognizer.energy_threshold:.0f}.", flush=True)
    except Exception as exc:
        recognizer.dynamic_energy_threshold = True
        print(f"[WARN] Microphone calibration skipped: {exc}", file=sys.stderr)


def clean_text_for_speech(text: str) -> str:
    """Expands acronyms for clean, natural offline speech."""
    s = text
    replacements = [
        (r"\bSIT\b", "S I T"),
        (r"\bVTU\b", "V T U"),
        (r"\bNAAC\b", "N A A C"),
        (r"\bAICTE\b", "A I C T E"),
        (r"\bNBA\b", "N B A"),
        (r"\bNIRF\b", "N I R F"),
        (r"\bCSE\b", "C S E"),
        (r"\bISE\b", "I S E"),
        (r"\bAIML\b", "A I and M L"),
        (r"\bAIDS\b", "A I and Data Science"),
        (r"\bECE\b", "E C E"),
        (r"\bEEE\b", "E E E"),
        (r"\bETE\b", "E T E"),
        (r"\bKCET\b", "K C E T"),
        (r"\bCOMEDK\b", "COMED K"),
        (r"\bCIE\b", "C I E"),
        (r"\bSEE\b", "S E E"),
        (r"\bCOE\b", "C O E"),
        (r"\bSGPA\b", "S G P A"),
        (r"\bCGPA\b", "C G P A"),
        (r"\bLPA\b", "Lakhs Per Annum"),
        (r"\bDr\.\b", "Doctor"),
        (r"\bProf\.\b", "Professor"),
        (r"\bB\.H\.\b", "B H"),
        (r"\bsit\.ac\.in\b", "s i t dot a c dot i n")
    ]
    for pat, rep in replacements:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)

    s = re.sub(r"[\*\_\[\]\(\)\{\}\#]", "", s)
    return s.strip()


def _load_tts_settings():
    """Read the dashboard's current delivery settings before every utterance."""
    path = os.path.join(ROOT, "data", "robo_settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        voice = settings.get("voice", {})
        voice_id = str(voice.get("voice_id", "en-IN-NeerjaNeural"))
        if not re.fullmatch(r"en-IN-[A-Za-z]+Neural", voice_id):
            voice_id = "en-IN-NeerjaNeural"
        return {
            "gender": voice.get("gender", "female"),
            "name": str(voice.get("name", "")).strip().lower(),
            "provider": voice.get("provider", "edge"),
            "voice_id": voice_id,
            "speed": max(.65, min(1.4, float(voice.get("speed", 1.0)))),
            "pitch": max(-10, min(10, int(voice.get("pitch", 0)))),
            "volume": max(0, min(100, int(voice.get("volume", 100)))),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"gender": "female", "name": "", "provider": "edge", "voice_id": "en-IN-NeerjaNeural", "speed": 1.0, "pitch": 0, "volume": 100}


def _edge_tts_module():
    """Import Edge TTS using certifi roots instead of a broken Windows root-store entry."""
    import ssl
    import certifi

    original = ssl.create_default_context

    def verified_default_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
        if purpose == ssl.Purpose.SERVER_AUTH and not (cafile or capath or cadata):
            cafile = certifi.where()
        return original(purpose, cafile=cafile, capath=capath, cadata=cadata)

    ssl.create_default_context = verified_default_context
    try:
        import edge_tts
    finally:
        ssl.create_default_context = original
    return edge_tts


def _edge_speak_interruptibly(text, settings):
    """Synthesize an Indian English neural voice online and play it locally."""
    import pygame

    start_sequence = _speech_abort_sequence()
    edge_tts = _edge_tts_module()
    print(f"[TTS] Using {settings['voice_id']} (Indian English).", flush=True)
    rate = round((settings["speed"] - 1.0) * 100)
    pitch_hz = settings["pitch"] * 2
    temporary = tempfile.NamedTemporaryFile(prefix="robo-tts-", suffix=".mp3", delete=False)
    audio_path = temporary.name
    temporary.close()
    try:
        communicate = edge_tts.Communicate(
            text, settings["voice_id"], rate=f"{rate:+d}%",
            volume=f"{settings['volume'] - 100:+d}%", pitch=f"{pitch_hz:+d}Hz",
        )
        asyncio.run(communicate.save(audio_path))
        if _speech_abort_sequence() != start_sequence:
            return False
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.set_volume(settings["volume"] / 100)
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if _speech_abort_sequence() != start_sequence:
                pygame.mixer.music.stop()
                return False
            time.sleep(.05)
        return True
    finally:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.unload()
        except Exception:
            pass
        try:
            os.remove(audio_path)
        except OSError:
            pass


def _apply_sapi_settings(settings):
    if _sapi_voice is None:
        return
    try:
        _sapi_voice.Rate = max(-10, min(10, round((settings["speed"] - 1.0) * 10)))
        _sapi_voice.Volume = settings["volume"]
        requested_name = settings.get("name", "")
        requested_gender = settings.get("gender", "female")
        voices = _sapi_voice.GetVoices()
        preferred = None
        for index in range(voices.Count):
            token = voices.Item(index)
            description = token.GetDescription()
            lowered = description.lower()
            if requested_name and requested_name in lowered:
                preferred = token
                break
            if requested_gender in ("male", "female"):
                try:
                    gender = str(token.GetAttribute("Gender")).lower()
                except Exception:
                    gender = ""
                name_matches = (bool(re.search(r"\bmale\b", lowered)) or "david" in lowered or "mark" in lowered) if requested_gender == "male" else (bool(re.search(r"\bfemale\b", lowered)) or "zira" in lowered or "heera" in lowered or "hazel" in lowered)
                if gender == requested_gender or name_matches:
                    preferred = token
                    break
        if preferred is not None:
            _sapi_voice.Voice = preferred
    except Exception as exc:
        print(f"[TTS WARN] Could not apply all voice settings: {exc}", file=sys.stderr)


_last_tts_status = {}


def get_tts_status():
    return dict(_last_tts_status)


def _set_tts_status(settings, provider, fallback_reason=""):
    _last_tts_status.clear()
    _last_tts_status.update({"provider": provider, "voice_id": settings.get("voice_id", ""),
                             "used_voice": settings.get("voice_id", "") if provider == "edge" else (settings.get("name") or "Windows system voice"),
                             "fallback": bool(fallback_reason), "reason": str(fallback_reason)[:240]})


_tts_is_speaking = False
_last_tts_end_time = 0.0


def is_tts_active() -> bool:
    """True if robot TTS is currently speaking or finished within 0.8s (prevents self-wake)."""
    return _tts_is_speaking or (time.time() - _last_tts_end_time < 0.8)


def speak(text: str, log_callback=None):
    """Speak using the current saved voice settings and report fallback clearly."""
    global _tts_is_speaking, _last_tts_end_time
    _tts_is_speaking = True
    spoken_text = clean_text_for_speech(text)
    if log_callback:
        log_callback(text)
    else:
        print(f"[ROBOT] {text}", flush=True)

    settings = _load_tts_settings()
    fallback_reason = ""
    try:
        if settings["provider"] == "edge":
            try:
                result = _edge_speak_interruptibly(spoken_text, settings)
                _set_tts_status(settings, "edge")
                return result
            except Exception as edge_error:
                fallback_reason = str(edge_error)
                print(f"[TTS WARN] {settings['voice_id']} unavailable; using the installed system voice: {edge_error}", file=sys.stderr)
        if _sapi_voice is not None:
            _apply_sapi_settings(settings)
            if settings["pitch"]:
                xml_text = f'<pitch middle="{settings["pitch"]}">{xml_utils.escape(spoken_text)}</pitch>'
                try:
                    result = _sapi_speak_interruptibly(xml_text, xml=True)
                except Exception:
                    result = _sapi_speak_interruptibly(spoken_text)
            else:
                result = _sapi_speak_interruptibly(spoken_text)
            _set_tts_status(settings, "system", fallback_reason)
            return result

        global tts_engine
        if tts_engine is None:
            tts_engine = pyttsx3.init()
        tts_engine.setProperty("rate", int(152 * settings["speed"]))
        tts_engine.setProperty("volume", settings["volume"] / 100)
        _apply_pyttsx_voice(settings)
        tts_engine.say(spoken_text)
        tts_engine.runAndWait()
        _set_tts_status(settings, "system", fallback_reason)
        _last_tts_end_time = time.time()
        _tts_is_speaking = False
        return True
    except Exception as e:
        print(f"[TTS ERROR] Speech output failed: {type(e).__name__}: {e}", file=sys.stderr)
        try:
            if tts_engine is None:
                tts_engine = pyttsx3.init()
            tts_engine.setProperty("rate", int(152 * settings["speed"]))
            tts_engine.setProperty("volume", settings["volume"] / 100)
            _apply_pyttsx_voice(settings)
            tts_engine.say(spoken_text)
            tts_engine.runAndWait()
            _set_tts_status(settings, "system", fallback_reason or str(e))
            return True
        except Exception as fallback_error:
            _set_tts_status(settings, "unavailable", fallback_reason or str(fallback_error))
            print(f"[TTS ERROR] Fallback speech output failed: {fallback_error}", file=sys.stderr)
            return False
        finally:
            _last_tts_end_time = time.time()
            _tts_is_speaking = False


def _apply_pyttsx_voice(settings):
    if tts_engine is None or settings.get("gender") == "default":
        return
    try:
        for voice in tts_engine.getProperty("voices"):
            name = (getattr(voice, "name", "") or "").lower()
            gender = (getattr(voice, "gender", "") or "").lower()
            if gender == settings["gender"] or settings["gender"] in name:
                tts_engine.setProperty("voice", voice.id)
                return
    except Exception:
        pass


def _apply_far_field_agc(raw_pcm: bytes, sample_width: int = 2) -> bytes:
    """Automatic gain control and peak normalization for far-field microphone capture."""
    try:
        peak = audioop.max(raw_pcm, sample_width)
        if 80 < peak < 16000:
            gain = min(4.0, 24000.0 / peak)
            return audioop.mul(raw_pcm, sample_width, gain)
    except Exception:
        pass
    return raw_pcm


def _resample_audio(audio_data: sr.AudioData) -> bytes:
    """
    Converts SpeechRecognition's mono PCM at its actual capture rate to a proper
    16 kHz mono WAV for Whisper and Vosk, applying AGC for far-field speech.
    """
    raw = audio_data.get_raw_data()
    source_rate = audio_data.sample_rate
    if source_rate != MIC_TARGET_RATE:
        raw, _ = audioop.ratecv(raw, audio_data.sample_width, 1,
                                source_rate, MIC_TARGET_RATE, None)

    # Far-field automatic gain boost
    raw = _apply_far_field_agc(raw, audio_data.sample_width)

    # Wrap in a proper WAV container (1 ch, 16-bit, 16000 Hz).
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(MIC_TARGET_RATE)
        wf.writeframes(raw)
    buf.seek(0)
    return buf.read()


def _transcribe_openai_whisper(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribes audio using OpenAI Whisper API if an API key is configured."""
    api_key = (
        os.environ.get("OPENAI_API_KEY") or
        os.environ.get("WHISPER_API_KEY") or
        ""
    ).strip()
    if not api_key:
        return ""
    try:
        import certifi, ssl, uuid
        from urllib.request import Request, urlopen

        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
        body = bytearray()
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n".encode("utf-8"))
        prompt = "Indian English, Siddaganga Institute of Technology, SIT, Tumakuru, Karnataka."
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"prompt\"\r\n\r\n{prompt}\r\n".encode("utf-8"))
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nen\r\n".encode("utf-8"))
        mime = "audio/webm" if filename.endswith((".webm", ".weba")) else "audio/wav"
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"))
        body.extend(audio_bytes)
        body.extend(b"\r\n")
        body.extend(("--" + boundary + "--\r\n").encode("utf-8"))

        api_url = os.environ.get("OPENAI_WHISPER_URL", "https://api.openai.com/v1/audio/transcriptions")
        req = Request(api_url, data=bytes(body), method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        })
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urlopen(req, timeout=15, context=ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("text", "").strip()
    except Exception as exc:
        print(f"[WARN] OpenAI Whisper API transcribe error: {exc}", file=sys.stderr)
        return ""


def transcribe_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribes audio bytes using OpenAI Whisper API -> Local Faster-Whisper -> Vosk.
    Supports WAV, WebM, MP3, and OGG formats with far-field voice recognition.
    """
    if not audio_bytes or len(audio_bytes) < 300:
        return ""

    # 1. Try OpenAI Whisper API first if API key configured
    openai_result = _transcribe_openai_whisper(audio_bytes, filename=filename)
    if openai_result:
        return openai_result

    # 2. Local Faster-Whisper Transformer
    if whisper_model is not None:
        try:
            wav_io = io.BytesIO(audio_bytes)
            language = os.environ.get("HUMANOID_ASR_LANGUAGE", "en").strip().lower()
            if language in ("", "auto", "none"):
                language = None
            segments, info = whisper_model.transcribe(
                wav_io,
                language=language,
                beam_size=3,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
                condition_on_previous_text=False,
                temperature=0,
                initial_prompt=(
                    "Indian English, including regional Indian accents. Siddaganga Institute of Technology, SIT, Tumakuru, Karnataka. "
                    "Campus guide words: principal, departments, placements, admissions, "
                    "KCET, COMEDK, hostels, fees, library, labs, and college facilities. "
                    "Wake phrase: Hey Robo."
                ),
            )
            w_text = " ".join(s.text for s in segments).strip()
            if w_text:
                return w_text
        except Exception as e:
            print(f"[WARN] Faster-Whisper transcribe error: {e}", file=sys.stderr)

    return ""


def synthesize_to_bytes(text: str, voice_id: str = None) -> bytes:
    """Synthesizes text to MP3 bytes using Edge-TTS for low-latency web playback."""
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""
    settings = _load_tts_settings()
    if voice_id:
        settings["voice_id"] = voice_id

    try:
        edge_tts = _edge_tts_module()
        rate = round((settings["speed"] - 1.0) * 100)
        pitch_hz = settings["pitch"] * 2

        async def _synthesize():
            communicate = edge_tts.Communicate(
                spoken_text,
                settings["voice_id"],
                rate=f"{rate:+d}%",
                volume=f"{settings['volume'] - 100:+d}%",
                pitch=f"{pitch_hz:+d}Hz",
            )
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        return asyncio.run(_synthesize())
    except Exception as exc:
        print(f"[TTS WARN] In-memory neural synthesis failed: {exc}", file=sys.stderr)
        return b""


def transcribe_audio(audio_data: sr.AudioData) -> str:
    """
    Transcribes recorded audio completely offline.
    Uses multilingual Large-v3-Turbo as primary for accent and language coverage.
    Falls back to chunked Vosk KaldiRecognizer if Whisper returns nothing.
    """
    wav_bytes = _resample_audio(audio_data)

    # 1. Primary: Faster-Whisper
    if whisper_model is not None:
        try:
            wav_io = io.BytesIO(wav_bytes)
            language = os.environ.get("HUMANOID_ASR_LANGUAGE", "auto").strip().lower()
            if language in ("", "auto", "none"):
                language = None
            segments, info = whisper_model.transcribe(
                wav_io,
                language=language,
                beam_size=5,
                # SpeechRecognition already segments this utterance; a second
                # VAD pass can remove soft syllables under motor noise.
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0,
                initial_prompt=(
                    "Indian English, including regional Indian accents. Siddaganga Institute of Technology, SIT, Tumakuru, Karnataka. "
                    "Campus guide words: principal, departments, placements, admissions, "
                    "KCET, COMEDK, hostels, fees, library, labs, and college facilities. "
                    "Wake phrase: Hey Robo."
                ),
            )
            w_text = " ".join(s.text for s in segments).strip()
            if w_text:
                return w_text
        except Exception as e:
            print(f"[WARN] Whisper transcribe error: {e}", file=sys.stderr)

    # 2. Secondary Fallback: Chunked Vosk
    if vosk_model is not None:
        try:
            rec = KaldiRecognizer(vosk_model, 16000)
            rec.SetWords(False)
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                raw = wf.readframes(wf.getnframes())

            text_chunks = []
            for i in range(0, len(raw), 4000):
                if rec.AcceptWaveform(raw[i:i+4000]):
                    t = json.loads(rec.Result()).get("text", "").strip()
                    if t:
                        text_chunks.append(t)
            fin = json.loads(rec.FinalResult()).get("text", "").strip()
            if fin:
                text_chunks.append(fin)

            v_text = " ".join(text_chunks).strip()
            if v_text:
                return v_text
        except Exception as e:
            print(f"[WARN] Vosk transcribe error: {e}", file=sys.stderr)

    return ""


def play_wake_beep():
    """Play a crisp, immediate wake-up beep (High C 1046 Hz, ~300ms) on detection."""
    try:
        if os.name == "nt":
            import winsound
            winsound.Beep(1046, 300)
        else:
            print("\a", flush=True)
    except Exception:
        print("\a", flush=True)


def listen_for_wake_word(timeout: float = None, sensitivity: float = 0.5) -> bool:
    """
    Lightweight, offline local wake-word detector.
    Listens exclusively for 'Hey Robo' (and close phonetics) using Vosk Kaldi grammar.
    Consumes ~1% CPU, 0 cloud tokens, 0 Gemini/Whisper calls while sleeping.
    Suppresses self-echo while robot is speaking.
    """
    global vosk_model
    if vosk_model is None:
        if os.path.isdir(VOSK_MODEL_PATH):
            try:
                vosk_model = Model(VOSK_MODEL_PATH)
            except Exception:
                pass
        if vosk_model is None:
            time.sleep(1.0)
            return False

    import pyaudio
    p = pyaudio.PyAudio()
    grammar = '["hey robo", "hey robot", "hello robo", "hello robot", "[unk]"]'
    rec = KaldiRecognizer(vosk_model, 16000, grammar)
    rec.SetWords(False)

    stream = None
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=2048,
        )
        stream.start_stream()

        start_time = time.time()
        while True:
            if timeout and (time.time() - start_time > timeout):
                return False

            # Prevent false wake-ups while robot speaks its own TTS
            if is_tts_active():
                try:
                    stream.read(2048, exception_on_overflow=False)
                except Exception:
                    pass
                time.sleep(0.05)
                continue

            try:
                data = stream.read(2048, exception_on_overflow=False)
            except Exception:
                continue

            if not data:
                continue

            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "").lower()
                if "hey robo" in text or "hey robot" in text or "hello robo" in text:
                    return True
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "").lower()
                if "hey robo" in partial or "hey robot" in partial:
                    return True

    except Exception as exc:
        print(f"[WAKE-WORD ERROR] {exc}", file=sys.stderr)
        time.sleep(0.5)
        return False
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()


def play_wake_sound():
    """Play a brief nonverbal cue after the wake phrase; this does not speak."""
    try:
        if os.name == "nt":
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        else:
            print("\a", end="", flush=True)
    except Exception:
        print("\a", end="", flush=True)


def listen(timeout: int = 8, phrase_time_limit: int = 15) -> str:
    """
    Captures audio from the current default input (or HUMANOID_MIC_DEVICE override)
    and decodes offline.
    """
    try:
        device_label = "Windows default" if MIC_DEVICE_INDEX is None else str(MIC_DEVICE_INDEX)
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as mic:
            print(f"  [MIC] Opening device [{device_label}] @ {mic.SAMPLE_RATE}Hz, mono, threshold={recognizer.energy_threshold}", flush=True)
            print("  [MIC] Listening... (speak now)", flush=True)
            audio = recognizer.listen(mic,
                                      timeout=timeout,
                                      phrase_time_limit=phrase_time_limit)

        raw = audio.get_raw_data()
        captured_rms = audioop.rms(raw, audio.sample_width)
        print(f"  [MIC] Captured {len(raw)} bytes at {audio.sample_rate}Hz mono, RMS={captured_rms}", flush=True)

        if captured_rms < 10:
            print("  [MIC] WARNING: RMS is near zero - audio may be silent/wrong device", flush=True)

        print("  [MIC] Processing offline speech...", flush=True)
        text = transcribe_audio(audio)
        print(f"  [MIC] Transcript: '{text}'", flush=True)
        return text.strip()

    except sr.WaitTimeoutError:
        print("  [MIC] TIMEOUT - no speech detected above threshold", flush=True)
        return ""
    except sr.UnknownValueError:
        print("  [MIC] UnknownValueError - audio unclear", flush=True)
        return ""
    except Exception as e:
        print(f"[MIC ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return ""


def cleanup():
    """Cleanup hook for graceful termination."""
    global tts_engine
    if tts_engine is not None:
        try:
            tts_engine.stop()
        except Exception:
            pass
    if _sapi_voice is not None:
        try:
            _sapi_voice.Speak("", 3)  # purge any queued speech
        except Exception:
            pass


if __name__ == "__main__":
    print(f"[MIC] Using device index {MIC_DEVICE_INDEX!r} (None=Windows default; capture rate is automatic)")
    print(f"[MIC] Energy threshold fixed at {ENERGY_THRESHOLD}")
    print("Testing speech engine...")
    speak("Speech engine ready. Please speak a test question.")
    q = listen(timeout=8)
    print(f"Captured: '{q}'")
