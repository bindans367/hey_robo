"""
voice_engine.py - Advanced Offline Hybrid Speech Engine (STT & TTS)
for SIT Humanoid Campus Assistant.

Combines:
- Audio capture from the current Windows default input device, using its native rate
  and SpeechRecognition's mono capture, with resampling to 16 kHz before Whisper
- Advanced offline Faster-Whisper tiny.en (CPU int8) for efficient English recognition
- Chunked Vosk KaldiRecognizer fallback
- Synchronous Windows SAPI Text-to-Speech with pyttsx3 fallback and acronym expansion

Mic notes:
  Use the current system default input rather than a device index from a different
  computer/session. SpeechRecognition captures mono audio at the device's native rate.
"""

import audioop
import asyncio
import base64
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import wave
import xml.sax.saxutils as xml_utils
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import pyttsx3
import numpy as np
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

# Load models on the first actual STT use, not on import. This lets dashboard
# TTS safely import this module without caching an STT-disabled instance.
whisper_model = None
whisper_model_name = None
vosk_model = None
_stt_models_loaded = False
_stt_model_lock = threading.Lock()
_stt_inference_lock = threading.Lock()


def _ensure_stt_models_loaded():
    """Load one cached CPU Whisper model and Vosk once, safely across threads."""
    global whisper_model, whisper_model_name, vosk_model, _stt_models_loaded
    if _stt_models_loaded:
        return
    with _stt_model_lock:
        if _stt_models_loaded:
            return
        print("[STT] Loading offline speech models once (CPU int8)...", flush=True)
        configured_model = os.environ.get("HUMANOID_WHISPER_MODEL", "").strip()
        candidates = [configured_model] if configured_model else []
        # English is the robot's default. tiny.en is cached and offers the
        # best startup/latency fit for this CPU; base.en is tried if available.
        for candidate in ("tiny.en", "base.en", "base", "large-v3-turbo"):
            if candidate not in candidates:
                candidates.append(candidate)
        for name in candidates:
            try:
                print(f"[STT] Loading Faster-Whisper '{name}'...", flush=True)
                whisper_model = WhisperModel(
                    name, device="cpu", compute_type="int8",
                    cpu_threads=max(2, min(4, os.cpu_count() or 4)), num_workers=1,
                    local_files_only=True,
                )
                whisper_model_name = name
                print(f"[STT] Faster-Whisper '{name}' ready.", flush=True)
                break
            except Exception as exc:
                print(f"[STT] Cached model '{name}' unavailable: {type(exc).__name__}.", flush=True)
                if configured_model == name:
                    try:
                        whisper_model = WhisperModel(
                            name, device="cpu", compute_type="int8",
                            cpu_threads=max(2, min(4, os.cpu_count() or 4)), num_workers=1,
                        )
                        whisper_model_name = name
                        print(f"[STT] Configured model '{name}' downloaded and ready.", flush=True)
                        break
                    except Exception as download_exc:
                        print(f"[ERROR] Configured Whisper model failed: {download_exc}", file=sys.stderr, flush=True)
        if os.path.isdir(VOSK_MODEL_PATH):
            try:
                vosk_model = Model(VOSK_MODEL_PATH)
                print("[STT] Vosk fallback ready.", flush=True)
            except Exception as exc:
                print(f"[ERROR] Vosk model failed to load: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if whisper_model is None:
            print("[ERROR] No local Faster-Whisper model loaded; Vosk is the only fallback.", file=sys.stderr, flush=True)
        _stt_models_loaded = True

# ---------------------------------------------------------------------------
# 3. SpeechRecognizer – fixed threshold, NO dynamic calibration
# ---------------------------------------------------------------------------
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True    # Follow changing motor / room noise
recognizer.energy_threshold         = ENERGY_THRESHOLD
recognizer.dynamic_energy_adjustment_damping = 0.08
recognizer.dynamic_energy_ratio = 1.5
recognizer.pause_threshold          = 1.45
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
_calibrated_device = object()


def calibrate_microphone():
    """Measure room noise once so the recognizer can set a suitable speech threshold."""
    global _calibrated, _calibrated_device
    if _calibrated and _calibrated_device == MIC_DEVICE_INDEX:
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
        _calibrated_device = MIC_DEVICE_INDEX
        print(f"Microphone calibrated; speech threshold={recognizer.energy_threshold:.0f}.", flush=True)
    except Exception as exc:
        recognizer.dynamic_energy_threshold = True
        _calibrated = True
        _calibrated_device = MIC_DEVICE_INDEX
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
        provider = voice.get("provider", "edge")
        voice_id = str(voice.get("voice_id", "Kore" if provider == "gemini" else "en-IN-NeerjaNeural"))
        if provider == "gemini":
            allowed = {"Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"}
            if voice_id not in allowed:
                voice_id = "Kore"
        elif not re.fullmatch(r"en-IN-[A-Za-z]+Neural", voice_id):
            voice_id = "en-IN-NeerjaNeural"
        online = settings.get("online", {})
        return {
            "gender": voice.get("gender", "female"),
            "name": str(voice.get("name", "")).strip().lower(),
            "provider": provider if provider in ("edge", "system", "gemini") else "edge",
            "voice_id": voice_id,
            "style": voice.get("style", "indian_clear"),
            "speed": max(.65, min(1.4, float(voice.get("speed", 1.0)))),
            "pitch": max(-10, min(10, int(voice.get("pitch", 0)))),
            "volume": max(0, min(100, int(voice.get("volume", 100)))),
            "api_key": str(online.get("api_key", "")).strip(),
            "tts_model": str(online.get("tts_model", "gemini-3.8-flash-tts")).strip() or "gemini-3.8-flash-tts",
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


def _gemini_synthesize(text, settings):
    """Generate natural Indian English speech with the saved Gemini API key."""
    api_key = settings.get("api_key", "")
    if not api_key:
        raise RuntimeError("Gemini TTS needs the API key saved in Voice & AI settings.")
    styles = {
        "indian_clear": "Speak in clear, natural Indian English as an educated and welcoming campus guide in Karnataka. Keep the Indian cadence authentic and subtle, never exaggerated. Use a gentle, measured pace and articulate names clearly.",
        "indian_warm": "Speak in warm, natural Indian English with a friendly, respectful campus-guide manner. Keep the local cadence authentic and subtle, never exaggerated. Sound conversational and unhurried.",
        "campus_formal": "Speak in polished Indian English for a college announcement. Be composed, respectful, and clearly articulated, with a natural Indian cadence and an even pace.",
        "indian_cheerful": "Speak in friendly, upbeat Indian English for welcoming students. Keep the local cadence authentic and subtle, never exaggerated; sound lively but not theatrical, with clear pronunciation.",
    }
    style = styles.get(settings.get("style"), styles["indian_clear"])
    if settings.get("speed", 1.0) < .9:
        style += " Slow down slightly and leave natural pauses between phrases."
    elif settings.get("speed", 1.0) > 1.12:
        style += " Keep a brisk but easy-to-follow pace."
    if settings.get("pitch", 0) <= -3:
        style += " Use a slightly lower vocal pitch."
    elif settings.get("pitch", 0) >= 3:
        style += " Use a slightly brighter, higher vocal placement."
    payload = {
        "model": settings.get("tts_model", "gemini-3.8-flash-tts"),
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": style}],
        }]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": settings.get("voice_id", "Kore")}]},
    }
    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key, "Api-Revision": "2026-05-20"},
    )
    try:
        try:
            import certifi, ssl
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_ctx = None
        with urlopen(request, timeout=45, context=ssl_ctx) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            details = json.loads(exc.read().decode("utf-8", errors="replace"))
            error = details.get("error", {})
            message = str(error.get("message", "")) if isinstance(error, dict) else ""
        except (ValueError, OSError):
            message = ""
        message = message.replace(api_key, "[hidden API key]")
        raise RuntimeError(f"Gemini TTS returned HTTP {exc.code}" + (f": {message[:220]}" if message else ".")) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Gemini TTS request failed: {str(exc)[:200]}") from exc
    audio = result.get("output_audio", {}).get("data") if isinstance(result.get("output_audio"), dict) else None
    if not audio:
        # The Interactions REST response stores audio under
        # steps[].content[] (the SDK's output_audio property is a convenience).
        for step in result.get("steps", []):
            if not isinstance(step, dict):
                continue
            for item in step.get("content", []):
                if isinstance(item, dict) and item.get("type") == "audio":
                    audio = item.get("data")
                    if audio:
                        break
            if audio:
                break
    if not audio:
        for item in result.get("outputs", []):
            if isinstance(item, dict) and item.get("type") == "audio":
                audio = item.get("data")
                if audio:
                    break
    if not audio:
        raise RuntimeError("Gemini returned no speech audio. Check that the selected TTS model is available for this API key.")
    try:
        return base64.b64decode(audio, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Gemini returned audio in an unrecognized format.") from exc


def _gemini_speak_interruptibly(text, settings):
    import pygame
    start_sequence = _speech_abort_sequence()
    audio_bytes = _gemini_synthesize(text, settings)
    if _speech_abort_sequence() != start_sequence:
        return False
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.set_volume(settings["volume"] / 100)
    pygame.mixer.music.load(io.BytesIO(audio_bytes))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if _speech_abort_sequence() != start_sequence:
            pygame.mixer.music.stop()
            return False
        time.sleep(.05)
    return True


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
                             "used_voice": (f"Gemini {settings.get('voice_id', '')}" if provider == "gemini" else settings.get("voice_id", "")) if provider in ("edge", "gemini") else (settings.get("name") or "Windows system voice"),
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
    fallback_reason = ""
    try:
        spoken_text = clean_text_for_speech(text)
        if log_callback:
            log_callback(text)
        else:
            print(f"[ROBOT] {text}", flush=True)

        settings = _load_tts_settings()
        print(f"[TTS] Speech generation started ({settings['provider']} / {settings['voice_id']}).", flush=True)
        if settings["provider"] == "gemini":
            try:
                result = _gemini_speak_interruptibly(spoken_text, settings)
                _set_tts_status(settings, "gemini")
                print("[TTS] Playback completed." if result else "[TTS] Playback interrupted.", flush=True)
                return result
            except Exception as gemini_error:
                fallback_reason = str(gemini_error)
                print(f"[TTS WARN] Gemini TTS unavailable; using the installed system voice: {gemini_error}", file=sys.stderr)
        if settings["provider"] == "edge":
            try:
                result = _edge_speak_interruptibly(spoken_text, settings)
                _set_tts_status(settings, "edge")
                print("[TTS] Playback completed." if result else "[TTS] Playback interrupted.", flush=True)
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
            print("[TTS] Playback completed." if result else "[TTS] Playback interrupted.", flush=True)
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
        print("[TTS] Playback completed.", flush=True)
        return True
    except Exception as e:
        print(f"[TTS ERROR] Speech output failed: {type(e).__name__}: {e}", file=sys.stderr)
        try:
            settings = locals().get("settings") or _load_tts_settings()
            spoken_text = locals().get("spoken_text") or clean_text_for_speech(text)
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
        # All providers, including Gemini, Edge, and SAPI, return through here.
        # Without this reset the local wake detector suppresses itself forever.
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
    # Faster-Whisper and Vosk get a canonical mono signed 16-bit WAV regardless
    # of the capture device's native sample width.
    raw = audio_data.get_raw_data(convert_width=2)
    source_rate = audio_data.sample_rate
    if source_rate != MIC_TARGET_RATE:
        raw, _ = audioop.ratecv(raw, 2, 1,
                                source_rate, MIC_TARGET_RATE, None)

    # Far-field automatic gain boost
    raw = _apply_far_field_agc(raw, 2)

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
        print("[STT] Empty/invalid transcript: audio payload is too short.", flush=True)
        return ""

    # 1. Try OpenAI Whisper API first if API key configured
    openai_result = _transcribe_openai_whisper(audio_bytes, filename=filename)
    if openai_result:
        print(f"[STT] Transcript: {openai_result}", flush=True)
        return openai_result

    # 2. Local Faster-Whisper Transformer
    _ensure_stt_models_loaded()
    if whisper_model is not None:
        try:
            wav_io = io.BytesIO(audio_bytes)
            language = os.environ.get("HUMANOID_ASR_LANGUAGE", "en").strip().lower()
            if language in ("", "auto", "none"):
                language = None
            with _stt_inference_lock:
                segments, info = whisper_model.transcribe(
                    wav_io,
                    language=language,
                    beam_size=3,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    temperature=0.0,
                    initial_prompt=(
                        "Conversational Indian English. Siddaganga Institute of Technology, SIT Tumakuru, Karnataka. "
                        "Campus guide: engineering admissions, placements, departments, coding, science, technology, general questions. "
                        "Wake word: Hey Robo."
                    ),
                )
                w_text = " ".join(s.text for s in segments).strip()
            if w_text:
                print(f"[STT] Transcript: {w_text}", flush=True)
                return w_text
        except Exception as e:
            print(f"[WARN] Faster-Whisper transcribe error: {e}", file=sys.stderr)

    # Browser MediaRecorder normally sends WebM/Opus. Decode it through
    # Faster-Whisper's bundled decoder before passing 16 kHz mono PCM to Vosk.
    # This gives the browser path the same offline fallback as the mic path.
    if vosk_model is not None:
        try:
            from faster_whisper.audio import decode_audio

            samples = decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)
            pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            v_text = _transcribe_vosk_pcm(pcm16)
            if v_text:
                print(f"[STT] Vosk transcript: {v_text}", flush=True)
                return v_text
        except Exception as e:
            print(f"[WARN] Vosk browser-audio fallback error: {e}", file=sys.stderr)

    print("[STT] Empty/invalid transcript: Whisper and Vosk returned no speech.", flush=True)
    return ""


def synthesize_to_bytes(text: str, voice_id: str = None) -> bytes:
    """Synthesizes text to MP3 bytes using Edge-TTS for low-latency web playback."""
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""
    settings = _load_tts_settings()
    if voice_id:
        settings["voice_id"] = voice_id
    print(f"[TTS] Speech generation started ({settings['provider']} / {settings['voice_id']}).", flush=True)

    gemini_unavailable = ""
    if settings["provider"] == "gemini":
        try:
            return _gemini_synthesize(spoken_text, settings)
        except Exception as exc:
            # Keep the web robot audible when Gemini quota, network, or model
            # availability temporarily blocks speech. Edge uses the selected
            # Indian English voice without consuming Gemini TTS quota.
            gemini_unavailable = str(exc)
            print(f"[TTS WARN] Gemini web TTS unavailable; trying the Indian English neural fallback: {exc}", file=sys.stderr)

    try:
        edge_tts = _edge_tts_module()
        rate = round((settings["speed"] - 1.0) * 100)
        pitch_hz = settings["pitch"] * 2
        edge_voice_id = settings["voice_id"] if settings["provider"] == "edge" else "en-IN-NeerjaNeural"

        async def _synthesize():
            communicate = edge_tts.Communicate(
                spoken_text,
                edge_voice_id,
                rate=f"{rate:+d}%",
                volume=f"{settings['volume'] - 100:+d}%",
                pitch=f"{pitch_hz:+d}Hz",
            )
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        result = asyncio.run(_synthesize())
        if not result:
            print("[ERROR] Indian English neural TTS returned no audio.", file=sys.stderr, flush=True)
        return result
    except Exception as exc:
        reason = f"Gemini: {gemini_unavailable}; fallback: {exc}" if gemini_unavailable else str(exc)
        print(f"[TTS WARN] In-memory neural synthesis failed: {reason}", file=sys.stderr)
        return b""


def transcribe_audio(audio_data: sr.AudioData) -> str:
    """
    Transcribes recorded audio completely offline.
    Uses cached Faster-Whisper tiny.en as primary for efficient English recognition.
    Falls back to chunked Vosk KaldiRecognizer if Whisper returns nothing.
    """
    wav_bytes = _resample_audio(audio_data)
    _ensure_stt_models_loaded()

    # 1. Primary: Faster-Whisper
    if whisper_model is not None:
        try:
            wav_io = io.BytesIO(wav_bytes)
            language = os.environ.get("HUMANOID_ASR_LANGUAGE", "en").strip().lower()
            if language in ("", "auto", "none"):
                language = None
            with _stt_inference_lock:
                segments, info = whisper_model.transcribe(
                    wav_io,
                    language=language,
                    beam_size=3,
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
                print(f"[STT] Transcript: {w_text}", flush=True)
                return w_text
        except Exception as e:
            print(f"[WARN] Whisper transcribe error: {e}", file=sys.stderr)

    # 2. Secondary Fallback: Chunked Vosk
    if vosk_model is not None:
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            v_text = _transcribe_vosk_pcm(raw)
            if v_text:
                print(f"[STT] Vosk transcript: {v_text}", flush=True)
                return v_text
        except Exception as e:
            print(f"[WARN] Vosk transcribe error: {e}", file=sys.stderr)

    return ""


def _transcribe_vosk_pcm(raw_pcm: bytes) -> str:
    """Decode mono 16 kHz signed PCM with the already-loaded Vosk model."""
    if not raw_pcm or vosk_model is None:
        return ""
    rec = KaldiRecognizer(vosk_model, 16000)
    rec.SetWords(False)
    text_chunks = []
    for i in range(0, len(raw_pcm), 4000):
        if rec.AcceptWaveform(raw_pcm[i:i + 4000]):
            text = json.loads(rec.Result()).get("text", "").strip()
            if text:
                text_chunks.append(text)
    final_text = json.loads(rec.FinalResult()).get("text", "").strip()
    if final_text:
        text_chunks.append(final_text)
    return " ".join(text_chunks).strip()


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
    _ensure_stt_models_loaded()
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
        device_info = (p.get_device_info_by_index(MIC_DEVICE_INDEX)
                       if MIC_DEVICE_INDEX is not None else p.get_default_input_device_info())
        device_index = int(device_info["index"])
        native_rate = int(device_info.get("defaultSampleRate", 16000))
        try:
            can_use_16k = p.is_format_supported(
                16000, input_device=device_index, input_channels=1, input_format=pyaudio.paInt16)
        except (ValueError, OSError):
            can_use_16k = False
        capture_rate = 16000 if can_use_16k else native_rate
        if capture_rate <= 0:
            raise RuntimeError(f"Invalid microphone sample rate: {capture_rate}")
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=capture_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=2048,
        )
        print(f"[WAKE] Mic device {device_index} capturing mono at {capture_rate} Hz.", flush=True)
        stream.start_stream()

        start_time = time.time()
        resample_state = None
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
            if capture_rate != 16000:
                data, resample_state = audioop.ratecv(data, 2, 1, capture_rate, 16000, resample_state)
                if not data:
                    continue

            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "").lower()
                if "hey robo" in text or "hey robot" in text or "hello robo" in text:
                    print(f"[WAKE] Wake word detected: {text}", flush=True)
                    return True
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "").lower()
                if "hey robo" in partial or "hey robot" in partial:
                    print(f"[WAKE] Wake word detected: {partial}", flush=True)
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


def listen(timeout: int = 8, phrase_time_limit: int = 15, offline_only: bool = False) -> str:
    """
    Captures audio from the current default input (or HUMANOID_MIC_DEVICE override)
    and decodes offline.
    """
    try:
        if _calibrated_device != MIC_DEVICE_INDEX:
            calibrate_microphone()
        device_label = "Windows default" if MIC_DEVICE_INDEX is None else str(MIC_DEVICE_INDEX)
        print("[RECORD] Recording started; waiting for speech and end-of-utterance silence.", flush=True)
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as mic:
            print(f"  [MIC] Opening device [{device_label}] @ {mic.SAMPLE_RATE}Hz, mono, threshold={recognizer.energy_threshold}", flush=True)
            print("  [MIC] Listening... (speak now)", flush=True)
            audio = recognizer.listen(mic,
                                      timeout=timeout,
                                      phrase_time_limit=phrase_time_limit)

        raw = audio.get_raw_data()
        captured_rms = audioop.rms(raw, audio.sample_width)
        duration = len(raw) / max(1, audio.sample_rate * audio.sample_width)
        print(f"[RECORD] Recording stopped: {duration:.2f}s, {len(raw)} bytes, {audio.sample_rate}Hz mono, RMS={captured_rms}.", flush=True)

        if duration < 0.30 or len(raw) < 4800 or captured_rms < 8:
            print("[STT] Empty/invalid transcript: captured audio is too short or too quiet.", flush=True)
            return ""

        print("[STT] Transcription started.", flush=True)
        settings = None
        try:
            import robo_brain_core as core
            settings = core.get_settings()
            microphone = settings.get("microphone", {})
            stt_provider = microphone.get("transcription_provider", "auto")
            use_gemini = (not offline_only) and (
                stt_provider == "gemini" or (stt_provider == "auto" and settings.get("mode") == "online"))
            if use_gemini:
                try:
                    print("[GEMINI] Sending captured transcript audio for transcription.", flush=True)
                    # Use a canonical PCM WAV; this keeps mic rate/channel details
                    # out of the cloud request and works with the recognizer's 16 kHz input.
                    text = core.transcribe_with_gemini(_resample_audio(audio), "audio/wav", (
                        "Siddaganga Institute of Technology", "SIT", "Tumakuru", "Karnataka",
                        "KCET", "COMEDK", "VTU", "CSE", "ISE", "AIML", "AIDS", "ECE", "EEE",
                        "principal", "placements", "hostel", "admissions", "Halcyon", "Birla Auditorium",
                    ))
                except Exception as exc:
                    print(f"[ERROR] Gemini STT failed; using local Faster-Whisper: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                    text = transcribe_audio(audio)
            else:
                text = transcribe_audio(audio)
        except Exception as exc:
            print(f"[ERROR] STT routing failed; using local Faster-Whisper: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            text = transcribe_audio(audio)
        text = text.strip()
        # Whisper can hallucinate greeting loops on silence, room noise, or the
        # wake beep. Do not let those transcripts trigger greeting answers.
        words = re.findall(r"[a-z0-9']+", text.casefold())
        if len(words) >= 8:
            counts = {word: words.count(word) for word in set(words)}
            unique_ratio = len(counts) / len(words)
            most_repeated = max(counts.values(), default=0)
            if unique_ratio < 0.45 and most_repeated >= 5:
                print("[STT] Empty/invalid transcript: repetitive recognition/noise.", flush=True)
                return ""
        if not text:
            print("[STT] Empty/invalid transcript.", flush=True)
        else:
            print(f"[STT] Transcript: {text}", flush=True)
        return text.strip()

    except sr.WaitTimeoutError:
        print("[RECORD] Recording stopped: timed out before speech was detected.", flush=True)
        print("[STT] Empty/invalid transcript.", flush=True)
        return ""
    except sr.UnknownValueError:
        print("[STT] Empty/invalid transcript: speech could not be understood.", flush=True)
        return ""
    except Exception as e:
        print(f"[ERROR] Microphone/STT failure: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
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
