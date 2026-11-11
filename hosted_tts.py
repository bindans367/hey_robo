"""Lightweight speech synthesis for the hosted Robo Brain service.

This module intentionally avoids importing the local microphone/STT stack
(PyAudio, Vosk, Faster-Whisper, pyttsx3), none of which is needed to return an
audio clip from the hosted web service.
"""
import asyncio
import base64
import html
import json
import os
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import robo_brain_core as core


def _gemini_key(settings):
    online = settings.get("online", {})
    host = (urlparse(online.get("base_url", "")).hostname or "").lower()
    return str(
        online.get("transcription_api_key")
        or os.environ.get("GEMINI_API_KEY")
        or (online.get("api_key", "") if host == "generativelanguage.googleapis.com" else "")
    ).strip()


def _gemini_audio(text, settings, voice):
    key = _gemini_key(settings)
    if not key:
        raise RuntimeError("No Gemini speech key is configured; using the Indian English neural fallback.")
    styles = {
        "indian_clear": "Speak in clear, natural Indian English as a welcoming campus guide in Karnataka. Use a gentle pace and articulate names clearly.",
        "indian_warm": "Speak in warm, natural Indian English with a friendly, respectful campus-guide manner.",
        "campus_formal": "Speak in polished Indian English for a college announcement, composed and clearly articulated.",
        "indian_cheerful": "Speak in friendly, upbeat Indian English for welcoming students; sound lively but not theatrical.",
    }
    style = styles.get(voice.get("style"), styles["indian_clear"])
    speed = float(voice.get("speed", 1.0))
    if speed < .9:
        style += " Slow down slightly and leave natural pauses between phrases."
    elif speed > 1.12:
        style += " Keep a brisk but easy-to-follow pace."
    pitch = int(voice.get("pitch", 0))
    if pitch <= -3:
        style += " Use a slightly lower vocal pitch."
    elif pitch >= 3:
        style += " Use a slightly brighter, higher vocal placement."
    payload = {
        "model": settings.get("online", {}).get("tts_model", "gemini-3.8-flash-tts"),
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": style}],
        }]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice.get("voice_id", "Kore")}]},
    }
    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key, "Api-Revision": "2026-05-20"},
    )
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    try:
        with urlopen(request, timeout=45, context=context) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            error_data = json.loads(exc.read().decode("utf-8", errors="replace"))
            message = str(error_data.get("error", {}).get("message", ""))
        except (ValueError, OSError, AttributeError):
            message = ""
        message = message.replace(key, "[hidden API key]")
        raise RuntimeError(f"Gemini TTS HTTP {exc.code}" + (f": {message[:180]}" if message else ".")) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Gemini TTS request failed: {str(exc)[:180]}") from exc

    audio = result.get("output_audio", {}).get("data") if isinstance(result.get("output_audio"), dict) else None
    if not audio:
        for step in result.get("steps", []):
            if isinstance(step, dict):
                for item in step.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "audio" and item.get("data"):
                        audio = item["data"]
                        break
            if audio:
                break
    if not audio:
        for item in result.get("outputs", []):
            if isinstance(item, dict) and item.get("type") == "audio" and item.get("data"):
                audio = item["data"]
                break
    if not audio:
        raise RuntimeError("Gemini returned no speech audio.")
    try:
        audio_bytes = base64.b64decode(audio, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Gemini returned an invalid audio payload.") from exc
    if not audio_bytes:
        raise RuntimeError("Gemini returned an empty audio payload.")
    return audio_bytes


def _edge_audio(text, voice):
    import edge_tts

    voice_id = str(voice.get("voice_id", ""))
    if not re.fullmatch(r"en-IN-[A-Za-z]+Neural", voice_id):
        voice_id = "en-IN-PrabhatNeural" if voice.get("gender") == "male" else "en-IN-NeerjaNeural"
    rate = round((float(voice.get("speed", 1.0)) - 1.0) * 100)
    pitch_hz = int(voice.get("pitch", 0)) * 2

    async def synthesize():
        communicator = edge_tts.Communicate(
            text, voice_id, rate=f"{rate:+d}%",
            volume=f"{int(voice.get('volume', 100)) - 100:+d}%",
            pitch=f"{pitch_hz:+d}Hz",
        )
        chunks = []
        async for chunk in communicator.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    audio = asyncio.run(synthesize())
    if not audio:
        raise RuntimeError("Indian English neural TTS returned no audio.")
    return audio


def synthesize_to_bytes(text):
    """Create selected voice audio, falling back from Gemini to Edge TTS."""
    spoken_text = re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()
    if not spoken_text:
        return b""
    settings = core.get_settings()
    voice = dict(settings.get("voice", {}))
    provider = voice.get("provider", "edge")
    if provider == "gemini":
        try:
            return _gemini_audio(spoken_text, settings, voice)
        except Exception as exc:
            print(f"[TTS WARN] Hosted Gemini TTS failed; trying Edge voice: {exc}", file=sys.stderr, flush=True)
    try:
        return _edge_audio(spoken_text, voice)
    except Exception as exc:
        print(f"[TTS ERROR] Hosted Edge TTS failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise RuntimeError(f"Hosted speech could not be generated. Gemini and Indian English fallback failed: {exc}") from exc
