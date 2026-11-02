"""Shared settings, answer routing, and conversation history for Robo Brain."""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "robo_settings.json")
HISTORY_PATH = os.path.join(DATA_DIR, "robo_history.json")
RUNTIME_PATH = os.path.join(DATA_DIR, "robo_runtime_state.json")
RUNTIME_CONTROL_PATH = os.path.join(DATA_DIR, "robo_runtime_control.json")
_lock = threading.RLock()
_mic_turn_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "mode": "offline",
    "system_prompt": "You are Robo, a friendly, clear, respectful humanoid campus guide for Siddaganga Institute of Technology. Speak in simple natural language. For SIT facts, use the supplied knowledge context and never invent people, dates, numbers, or policies. If the answer is unknown, say so and suggest checking with the college.",
    "voice": {"gender": "female", "name": "", "provider": "edge", "voice_id": "en-IN-NeerjaNeural", "speed": 1.0, "pitch": 0, "volume": 100},
    "local_llm": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:0.6b", "api_key": ""},
    "online": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.8-flash", "api_key": ""},
    "conversation": {
        "welcome": "Welcome to SIT. I’m Robo, your campus guide.",
        "wake_phrases": ["hey robo", "hey robot", "hello robo", "hello robot", "hit o boo", "hitable", "here it will go"],
        "wake_reply": "I’m listening. Ask me about Siddaganga Institute of Technology.",
        "stop_phrases": ["robo stop", "robot stop", "hey robo stop", "hey robot stop", "exit", "quit", "terminate", "please stop"],
        "farewell": "Goodbye! Have a productive day at Siddaganga Institute of Technology.",
        "thank_reply": "You’re very welcome! I’m happy to help. Is there anything else you’d like to know about SIT?",
        "no_match_reply": "I’m not quite sure I understood that. Could you ask it another way? I can help with SIT courses, admissions, hostels, placements, clubs, and campus services.",
        "pause_reply": "Conversation paused. Say ‘Hey Robo’ whenever you need me again.",
        "listen_timeout": 10, "phrase_time_limit": 15, "silent_turns": 6, "sleep_after_answer": 2,
        "mood": "friendly", "humor_enabled": False, "humor_frequency": 5,
    },
    "microphone": {"device_index": -1, "energy_threshold": 300},
}

def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return fallback

def atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    # On Windows, os.replace can raise PermissionError if the dashboard or reader
    # has a shared read lock open at the exact millisecond of replacement.
    for attempt in range(5):
        try:
            os.replace(temp, path)
            return
        except OSError:
            time.sleep(0.05 * (attempt + 1))
    try:
        os.replace(temp, path)
    except OSError:
        try:
            os.remove(temp)
        except OSError:
            pass

def get_settings():
    with _lock:
        saved = _read_json(SETTINGS_PATH, {})
        merged = json.loads(json.dumps(DEFAULT_SETTINGS))
        if isinstance(saved, dict):
            for key in ("mode", "system_prompt"):
                if key in saved:
                    merged[key] = saved[key]
            for key in ("voice", "online", "local_llm", "conversation", "microphone"):
                if isinstance(saved.get(key), dict):
                    merged[key].update(saved[key])
        if os.environ.get("ROBO_BRAIN_API_KEY"):
            merged["online"]["api_key"] = os.environ["ROBO_BRAIN_API_KEY"]
        if merged["mode"] not in ("offline", "local", "online"):
            merged["mode"] = "offline"
        voice = merged["voice"]
        voice_id = str(voice.get("voice_id", ""))
        if voice.get("provider", "edge") != "system" and not re.fullmatch(r"en-IN-[A-Za-z]+Neural", voice_id):
            voice["provider"] = "edge"
            voice["voice_id"] = "en-IN-NeerjaNeural"
            voice["gender"] = "female"
            voice["name"] = "en-IN-NeerjaNeural"
        return merged

def save_settings(new_settings):
    settings = get_settings()
    for key in ("mode", "system_prompt"):
        if key in new_settings:
            settings[key] = new_settings[key]
    for key in ("voice", "online", "local_llm", "conversation", "microphone"):
        if isinstance(new_settings.get(key), dict):
            settings[key].update(new_settings[key])
    settings["mode"] = settings["mode"] if settings["mode"] in ("offline", "local", "online") else "offline"
    voice = settings["voice"]
    voice["gender"] = voice.get("gender", "female") if voice.get("gender") in ("female", "male", "default") else "female"
    known_voice_genders = {
        "en-IN-AaravNeural": "male",
        "en-IN-AashiNeural": "female",
        "en-IN-AartiNeural": "female",
        "en-IN-ArjunNeural": "male",
        "en-IN-AnanyaNeural": "female",
        "en-IN-KavyaNeural": "female",
        "en-IN-KunalNeural": "male",
        "en-IN-NeerjaNeural": "female",
        "en-IN-PrabhatNeural": "male",
        "en-IN-RehaanNeural": "male",
    }
    voice_id = str(voice.get("voice_id", "en-IN-NeerjaNeural"))
    voice["voice_id"] = voice_id if re.fullmatch(r"en-IN-[A-Za-z]+Neural", voice_id) else "en-IN-NeerjaNeural"
    voice["provider"] = "system" if voice.get("provider") == "system" else "edge"
    if voice["provider"] == "edge":
        voice["gender"] = known_voice_genders.get(voice["voice_id"], voice.get("gender", "female"))
        voice["name"] = voice["voice_id"]
    voice["speed"] = max(0.65, min(1.4, float(voice.get("speed", 1.0))))
    voice["pitch"] = max(-10, min(10, int(voice.get("pitch", 0))))
    voice["volume"] = max(0, min(100, int(voice.get("volume", 100))))
    for section in ("online", "local_llm"):
        settings[section]["base_url"] = str(settings[section].get("base_url", "")).rstrip("/")
        settings[section]["model"] = str(settings[section].get("model", "")).strip()
        settings[section]["api_key"] = str(settings[section].get("api_key", "")).strip()
    conversation = settings["conversation"]
    for key in ("welcome", "wake_reply", "farewell", "thank_reply", "no_match_reply", "pause_reply"):
        conversation[key] = str(conversation.get(key, DEFAULT_SETTINGS["conversation"][key])).strip()[:2000] or DEFAULT_SETTINGS["conversation"][key]
    for key in ("wake_phrases", "stop_phrases"):
        values = conversation.get(key, DEFAULT_SETTINGS["conversation"][key])
        if isinstance(values, str):
            values = values.splitlines()
        conversation[key] = list(dict.fromkeys(str(v).strip().lower() for v in values if str(v).strip()))[:40] or DEFAULT_SETTINGS["conversation"][key]
    conversation["listen_timeout"] = max(2, min(30, int(conversation.get("listen_timeout", 8))))
    conversation["phrase_time_limit"] = max(2, min(30, int(conversation.get("phrase_time_limit", 15))))
    conversation["silent_turns"] = max(1, min(10, int(conversation.get("silent_turns", 3))))
    conversation["sleep_after_answer"] = max(0, min(15, float(conversation.get("sleep_after_answer", 2))))
    conversation["mood"] = conversation.get("mood", "friendly") if conversation.get("mood") in ("friendly", "cheerful", "playful") else "friendly"
    conversation["humor_enabled"] = bool(conversation.get("humor_enabled", False))
    conversation["humor_frequency"] = max(2, min(20, int(conversation.get("humor_frequency", 5))))
    microphone = settings["microphone"]
    microphone["device_index"] = int(microphone.get("device_index", -1))
    microphone["energy_threshold"] = max(50, min(4000, int(microphone.get("energy_threshold", 300))))
    with _lock:
        # The dashboard deliberately avoids returning a previously saved key to the browser.
        atomic_json(SETTINGS_PATH, settings)
    return settings

def publish_runtime(phase, transcript="", answer="", title="", detail=""):
    state = {"phase": str(phase), "transcript": str(transcript)[:3000], "answer": str(answer)[:6000],
             "title": str(title)[:200], "detail": str(detail)[:500],
             "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
    with _lock:
        atomic_json(RUNTIME_PATH, state)
    return state

def get_runtime():
    with _lock:
        state = _read_json(RUNTIME_PATH, {})
    return state if isinstance(state, dict) else {}

def request_speech_abort():
    with _lock:
        control = _read_json(RUNTIME_CONTROL_PATH, {"abort_seq": 0})
        control["abort_seq"] = int(control.get("abort_seq", 0)) + 1
        atomic_json(RUNTIME_CONTROL_PATH, control)
        return control["abort_seq"]

def speech_abort_sequence():
    control = _read_json(RUNTIME_CONTROL_PATH, {"abort_seq": 0})
    try:
        return int(control.get("abort_seq", 0))
    except (TypeError, ValueError):
        return 0

def get_history(limit=200):
    with _lock:
        events = _read_json(HISTORY_PATH, [])
    return events[-max(1, min(1000, int(limit))):][::-1]

def add_history(kind, text, answer="", source="dashboard", title=""):
    row = {"id": f"{time.time_ns()}", "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
           "kind": kind, "text": text, "answer": answer, "source": source, "title": title}
    with _lock:
        events = _read_json(HISTORY_PATH, [])
        events.append(row)
        atomic_json(HISTORY_PATH, events[-1000:])
    return row

def clear_history():
    with _lock:
        atomic_json(HISTORY_PATH, [])


def claim_microphone_turn(query, window_seconds=3.0):
    """Claim a microphone question once across Robo processes.

    A second bot process can occasionally survive a dashboard restart and hear
    the same utterance. The OS file lock makes the check/update atomic across
    processes; the short time window only suppresses near-simultaneous copies.
    """
    import hashlib
    normalized = " ".join(str(query).casefold().split())
    if not normalized:
        return False
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    lock_path = os.path.join(DATA_DIR, "robo_mic_turn.lock")
    state_path = os.path.join(DATA_DIR, "robo_mic_turn.json")
    os.makedirs(DATA_DIR, exist_ok=True)

    with _mic_turn_lock:
        try:
            handle = open(lock_path, "a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b" ")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            try:
                handle.close()
            except (UnboundLocalError, OSError):
                pass
            # If another process owns the guard, let that process answer.
            return False

        try:
            now = time.time()
            try:
                with open(state_path, "r", encoding="utf-8") as state_file:
                    previous = json.load(state_file)
            except (OSError, ValueError, TypeError):
                previous = {}
            try:
                previous_time = float(previous.get("time", 0))
            except (TypeError, ValueError):
                previous_time = 0
            if previous.get("key") == key and 0 <= now - previous_time < window_seconds:
                return False
            atomic_json(state_path, {"key": key, "time": now})
            return True
        finally:
            try:
                unlock()
            finally:
                handle.close()

def _offline_answer(query, matcher):
    result = matcher.search(query)
    result["mode"] = "offline"
    return result

def answer_query(query, matcher, source="dashboard"):
    settings = get_settings()
    local_result = matcher.search(query)
    normalized_query = " ".join(str(query).lower().split())
    joke_requested = any(phrase in normalized_query for phrase in ("tell me a joke", "make me laugh", "say something funny", "crack a joke"))
    jokes = [
        "Why did the student bring a ladder to class? They heard the grades were going up!",
        "Why was the computer cold at the lab? It left its Windows open.",
        "What did the campus map say to a lost student? I know the way around here.",
    ]
    # Offline mode is intentionally strict: even social prompts are handled by
    # the curated local matcher rather than accidentally invoking an LLM.
    if joke_requested and settings["mode"] == "offline":
        result = {"matched": True, "confidence": 100.0, "topic_id": "robo_joke", "title": "A little campus humor",
                  "answer": jokes[int(time.time()) % len(jokes)], "suggestions": [], "normalized_query": query, "mode": "offline"}
    elif settings["mode"] == "offline":
        result = local_result
        result["mode"] = "offline"
    else:
        mode = settings["mode"]
        llm = settings["local_llm"] if mode == "local" else settings["online"]
        key = llm.get("api_key", "").strip()
        host = urlparse(llm.get("base_url", "")).hostname or ""
        local_endpoint = host.lower() in ("localhost", "127.0.0.1", "::1")
        mode_name = "local Qwen/Ollama" if mode == "local" else "online model"
        if (not key and not local_endpoint) or not llm.get("model") or not llm.get("base_url"):
            result = {"matched": False, "confidence": 0.0, "topic_id": "llm_not_configured", "title": mode_name,
                      "answer": f"{mode_name.capitalize()} mode is selected, but its endpoint, model, or API key is missing. Please check Voice & AI settings.",
                      "suggestions": [], "normalized_query": query, "mode": mode, "notice": "Selected model is not configured."}
        else:
            context = local_result.get("answer", "") if local_result.get("matched") else "No direct answer was found in the local SIT knowledge base."
            mood_instruction = {
                "friendly": "Use a warm, friendly campus-guide voice.",
                "cheerful": "Sound upbeat and welcoming while staying clear and accurate.",
                "playful": "Use a light, playful campus-guide voice, but keep factual answers respectful and never let humor obscure the facts.",
            }.get(settings["conversation"].get("mood", "friendly"), "Use a warm, friendly campus-guide voice.")
            base_url = llm["base_url"].rstrip("/")
            parsed_endpoint = urlparse(base_url)
            is_ollama = mode == "local" and local_endpoint and parsed_endpoint.port == 11434
            if is_ollama:
                # Ollama's native API supports think=false for Qwen3, preventing
                # reasoning traces from leaking into Robo's spoken response.
                url = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}/api/chat"
                payload = {"model": llm["model"], "think": False, "stream": False, "messages": [
                    {"role": "system", "content": settings["system_prompt"] + "\n\n" + mood_instruction + "\n\nRelevant local SIT knowledge (use when relevant; do not contradict it):\n" + context},
                    {"role": "user", "content": query}], "options": {"temperature": 0.4}}
            else:
                url = base_url + "/chat/completions"
                payload = {"model": llm["model"], "messages": [
                    {"role": "system", "content": settings["system_prompt"] + "\n\n" + mood_instruction + "\n\nRelevant local SIT knowledge (use when relevant; do not contradict it):\n" + context},
                    {"role": "user", "content": query}], "temperature": 0.4}
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = "Bearer " + key
            request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers)
            try:
                ssl_ctx = None
                try:
                    import certifi, ssl
                    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
                except Exception:
                    pass
                with urlopen(request, timeout=60 if mode == "local" else 30, context=ssl_ctx) as response:
                    data = json.loads(response.read().decode("utf-8"))
                answer = (data["message"]["content"] if is_ollama else data["choices"][0]["message"]["content"]).strip()
                result = {"matched": True, "confidence": 100.0, "topic_id": "local_llm" if mode == "local" else "online_llm", "title": "Local Qwen" if mode == "local" else "Cloud language model",
                          "answer": answer, "suggestions": [], "normalized_query": query, "mode": mode}
            except (HTTPError, URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as exc:
                reason = str(exc)[:180]
                result = {"matched": False, "confidence": 0.0, "topic_id": "llm_unavailable", "title": mode_name,
                          "answer": f"I can't reach the selected {mode_name} right now. Please check that it is running and configured, then try again. {reason}",
                          "suggestions": [], "normalized_query": query, "mode": mode, "notice": f"Selected {mode_name} could not be reached."}
    conversation = settings["conversation"]
    # Reviewed answers already use a conversational voice. Avoid stacking a
    # generic opener on top of phrases such as “Sure…” or “Here’s a quick look”.
    if result.get("matched") and conversation["mood"] == "cheerful" and result.get("topic_id") not in ("thank_reply", "robo_joke"):
        result["answer"] = "Absolutely, happy to help! " + result.get("answer", "")
    elif result.get("matched") and conversation["mood"] == "playful" and result.get("topic_id") not in ("thank_reply", "robo_joke"):
        result["answer"] = "Let’s figure that out together! " + result.get("answer", "")
    if conversation["humor_enabled"] and result.get("matched") and result.get("topic_id") not in ("thank_reply", "robo_joke"):
        turns = sum(1 for row in get_history(1000) if row.get("kind") == "conversation")
        if (turns + 1) % conversation["humor_frequency"] == 0:
            result["answer"] += "\n\nAnd a tiny campus joke: Why did the student bring a ladder to class? They heard the grades were going up!"
    add_history("conversation", query, result.get("answer", ""), source, result.get("title", ""))
    return result

