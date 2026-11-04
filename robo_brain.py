"""Local web control panel and API for the SIT humanoid assistant.

Run with: python robo_brain.py
The service only listens on 127.0.0.1; open http://127.0.0.1:8765.
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote
from urllib.request import Request, urlopen

from matcher import matcher
import robo_brain_core as core

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
KNOWLEDGE_PATH = os.path.join(ROOT, "knowledge.json")
CUSTOMIZATION_PATH = os.path.join(ROOT, "data", "knowledge_dashboard_state.json")
SCRIPTS_PATH = os.path.join(ROOT, "data", "robo_saved_scripts.json")
speech_queue = queue.Queue()
robot_process = None
robot_output = None
robot_lock = threading.Lock()
last_tts_status = {}

def speech_worker():
    engine = None
    global last_tts_status
    while True:
        item = speech_queue.get()
        if item is None:
            return
        text, done = item
        try:
            if engine is None:
                # The dashboard needs SAPI only; don't load the Whisper model.
                previous = os.environ.get("HUMANOID_TTS_ONLY")
                os.environ["HUMANOID_TTS_ONLY"] = "1"
                try:
                    import voice_engine
                    engine = voice_engine
                finally:
                    if previous is None:
                        os.environ.pop("HUMANOID_TTS_ONLY", None)
                    else:
                        os.environ["HUMANOID_TTS_ONLY"] = previous
            done["spoken"] = engine.speak(text)
            last_tts_status = engine.get_tts_status()
            done["voice_status"] = dict(last_tts_status)
            done["ok"] = True
        except Exception as exc:
            done["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            done["event"].set()
            speech_queue.task_done()

threading.Thread(target=speech_worker, name="robo-speech", daemon=True).start()

def speak_and_wait(text):
    done = {"event": threading.Event()}
    speech_queue.put((text, done))
    if not done["event"].wait(timeout=120):
        raise TimeoutError("Speech did not finish in time")
    if done.get("error"):
        raise RuntimeError(done["error"])
    if done.get("voice_status"):
        with robot_lock:
            last_tts_status.update(done["voice_status"])
    return done.get("spoken") is not False

def read_knowledge():
    with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def write_knowledge(items, deleted_id=None, restored_id=None):
    core.atomic_json(KNOWLEDGE_PATH, items)
    saved = core._read_json(CUSTOMIZATION_PATH, {"overrides": [], "deleted": []})
    overrides = {entry.get("id"): entry for entry in saved.get("overrides", []) if entry.get("id")}
    for entry in items:
        if entry.get("updated_at"):
            overrides[entry["id"]] = entry
    deleted = set(saved.get("deleted", []))
    if deleted_id:
        deleted.add(deleted_id)
        overrides.pop(deleted_id, None)
    if restored_id:
        deleted.discard(restored_id)
    core.atomic_json(CUSTOMIZATION_PATH, {"overrides": list(overrides.values()), "deleted": sorted(deleted)})
    matcher.reload()

def robot_status():
    running = bool(robot_process and robot_process.poll() is None)
    return {"running": running, "pid": robot_process.pid if running else None,
            "activity": core.get_runtime()}

def read_scripts():
    scripts = core._read_json(SCRIPTS_PATH, [])
    return scripts if isinstance(scripts, list) else []

def start_robot(mode="voice"):
    global robot_process, robot_output
    with robot_lock:
        if robot_process and robot_process.poll() is None:
            return robot_status()
        if robot_output:
            robot_output.close()
        log_path = os.path.join(ROOT, "data", "robot_runtime.log")
        robot_output = open(log_path, "a", encoding="utf-8", buffering=1)
        command = [sys.executable, os.path.join(ROOT, "bot.py")]
        if mode == "ptt":
            command.append("--ptt")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        child_env = os.environ.copy()
        child_env.pop("HUMANOID_TTS_ONLY", None)
        core.publish_runtime("STARTING", detail="Starting Robo’s microphone and speech engine.")
        robot_process = subprocess.Popen(command, cwd=ROOT, stdout=robot_output,
                                         stderr=subprocess.STDOUT, creationflags=flags, env=child_env)
        # The Windows venv launcher may create a second Python process. Detect
        # the single-instance lock refusal promptly instead of showing a false start.
        time.sleep(0.5)
        if robot_process.poll() is not None:
            if robot_output:
                robot_output.close()
                robot_output = None
            core.publish_runtime("STOPPED", detail="Another Robo process already owns the microphone.")
            raise RuntimeError("Another Robo voice process is already active. Stop the older instance and try again.")
        return robot_status()

def stop_robot():
    global robot_process, robot_output
    with robot_lock:
        if robot_process and robot_process.poll() is None:
            if os.name == "nt":
                # Terminate the venv launcher and the real Python child together;
                # otherwise a detached child can keep the mic lock and talk on.
                try:
                    subprocess.run(["taskkill", "/PID", str(robot_process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                except (OSError, subprocess.TimeoutExpired):
                    robot_process.terminate()
            else:
                robot_process.terminate()
            try:
                robot_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                robot_process.kill()
                robot_process.wait(timeout=3)
        if robot_output:
            robot_output.close()
            robot_output = None
        return robot_status()

def safe_settings():
    settings = core.get_settings()
    for section in ("online", "local_llm"):
        settings[section]["api_key_set"] = bool(settings[section].get("api_key"))
        settings[section]["api_key"] = ""
    return settings

class Handler(BaseHTTPRequestHandler):
    server_version = "RoboBrain/1.0"

    def log_message(self, fmt, *args):
        print("[ROBO BRAIN] " + fmt % args)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("Request is too large")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/bootstrap":
            items = read_knowledge()
            categories = sorted({str(x.get("category", "general")) for x in items})
            return self.send_json({"knowledge": items, "settings": safe_settings(),
                                   "history": core.get_history(100), "categories": categories,
                                   "department_count": len(matcher.departments), "scripts": read_scripts()})
        if path == "/api/history":
            return self.send_json({"history": core.get_history(1000)})
        if path == "/api/status":
            return self.send_json({"robot": robot_status()})
        if path == "/api/health":
            return self.send_json({"status": "healthy", "service": "robo_brain", "version": "2.0.0"})
        if path == "/api/tts":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            text_to_speak = params.get("text", [""])[0].strip()
            if not text_to_speak:
                return self.send_json({"error": "Missing text parameter"}, 400)
            try:
                import voice_engine
                audio_bytes = voice_engine.synthesize_to_bytes(text_to_speak)
                if not audio_bytes:
                    return self.send_json({"error": "TTS synthesis returned no audio"}, 500)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            except Exception as exc:
                return self.send_json({"error": f"TTS error: {exc}"}, 500)
        if path.startswith("/api/"):
            return self.send_json({"error": "Not found"}, 404)
        if path == "/eyes":
            path = "/eyes.html"
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        rel = os.path.normpath(rel)
        target = os.path.abspath(os.path.join(WEB_DIR, rel))
        if not target.startswith(os.path.abspath(WEB_DIR) + os.sep) and target != os.path.join(WEB_DIR, "index.html"):
            return self.send_error(404)
        try:
            with open(target, "rb") as f:
                content = f.read()
            mime = "text/html; charset=utf-8" if target.endswith(".html") else "text/javascript; charset=utf-8" if target.endswith(".js") else "text/css; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        except OSError:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        content_type = self.headers.get("Content-Type", "").lower()
        length = int(self.headers.get("Content-Length", "0"))
        try:
            if path in ("/api/transcribe", "/api/ask-voice") and (content_type.startswith("audio/") or content_type.startswith("application/octet-stream")):
                if length > 25_000_000:
                    return self.send_json({"error": "Audio file too large"}, 400)
                audio_bytes = self.rfile.read(length)
                filename = "audio.webm" if "webm" in content_type else "audio.wav"
                import voice_engine
                transcript = voice_engine.transcribe_bytes(audio_bytes, filename=filename)
                
                if path == "/api/transcribe":
                    return self.send_json({"ok": True, "text": transcript})
                
                # /api/ask-voice: end-to-end low-latency processing
                if not transcript:
                    return self.send_json({"ok": False, "reason": "no_speech", "message": "No clear speech detected. Please speak closer or louder."})
                
                core.publish_runtime("THINKING", transcript=transcript, detail="Processing speech with AI...")
                settings = core.get_settings()
                conv = settings.get("conversation", {})
                norm_cmd = " ".join(re.sub(r"[^\w\s]", " ", transcript.lower()).split())
                
                # Check stop phrase
                if any(norm_cmd == p or norm_cmd.startswith(p + " ") for p in conv.get("stop_phrases", [])):
                    farewell = conv.get("farewell", "Goodbye!")
                    core.publish_runtime("SPEAKING", transcript=transcript, answer=farewell, title="Robo Stopped", detail="Voice session stopped by user.")
                    return self.send_json({
                        "ok": True,
                        "transcript": transcript,
                        "is_stop": True,
                        "answer": farewell,
                        "title": "Goodbye",
                        "audio_url": f"/api/tts?text={quote(farewell)}"
                    })
                
                result = core.answer_query(transcript, matcher, source="voice_web")
                ans_text = result.get("answer", "")
                core.publish_runtime("SPEAKING", transcript=transcript, answer=ans_text, title=result.get("title", ""), detail="Robo is speaking response.")
                return self.send_json({
                    "ok": True,
                    "transcript": transcript,
                    "result": result,
                    "answer": ans_text,
                    "title": result.get("title", ""),
                    "audio_url": f"/api/tts?text={quote(ans_text)}"
                })

            data = self.body_json()
            if path == "/api/settings":
                old = core.get_settings()
                incoming = data.get("settings", data)
                for section in ("online", "local_llm"):
                    if isinstance(incoming.get(section), dict) and not incoming[section].get("api_key"):
                        incoming[section]["api_key"] = old[section].get("api_key", "")
                settings = core.save_settings(incoming)
                return self.send_json({"ok": True, "settings": safe_settings()})
            if path == "/api/knowledge/save":
                item = data.get("item", {})
                item_id = str(item.get("id", "")).strip()
                title = str(item.get("title", "")).strip()
                answer = str(item.get("answer", "")).strip()
                if not re.fullmatch(r"[a-zA-Z0-9_-]{2,80}", item_id):
                    return self.send_json({"error": "Use a short ID with letters, numbers, hyphens, or underscores."}, 400)
                if not title or not answer:
                    return self.send_json({"error": "A title and answer are required."}, 400)
                keywords = item.get("keywords", [])
                if isinstance(keywords, str):
                    keywords = [s.strip() for s in keywords.splitlines() if s.strip()]
                keywords = list(dict.fromkeys(str(x).strip() for x in keywords if str(x).strip()))
                if not keywords:
                    keywords = [title]
                items = read_knowledge()
                entry = {"id": item_id, "title": title, "category": str(item.get("category", "general")).strip() or "general",
                         "keywords": keywords, "answer": answer,
                         "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                if item.get("sources"):
                    entry["sources"] = item["sources"]
                index = next((i for i, old in enumerate(items) if old.get("id") == item_id), None)
                if index is None:
                    items.append(entry)
                else:
                    items[index] = entry
                write_knowledge(items, restored_id=item_id)
                return self.send_json({"ok": True, "knowledge": items, "count": len(items)})
            if path == "/api/knowledge/delete":
                item_id = str(data.get("id", ""))
                items = [item for item in read_knowledge() if item.get("id") != item_id]
                write_knowledge(items, deleted_id=item_id)
                return self.send_json({"ok": True, "knowledge": items, "count": len(items)})
            if path == "/api/ask":
                query = str(data.get("query", "")).strip()
                if not query:
                    return self.send_json({"error": "Type a question first."}, 400)
                result = core.answer_query(query, matcher, source="dashboard")
                spoken = None
                if data.get("speak", True):
                    core.publish_runtime("SPEAKING", transcript=query, answer=result["answer"], title=result.get("title", ""), detail="Robo is speaking the dashboard answer.")
                    try:
                        spoken = speak_and_wait(result["answer"])
                    finally:
                        phase = "READY" if locals().get("spoken", True) else "INTERRUPTED"
                        core.publish_runtime(phase, transcript=query, answer=result["answer"], title=result.get("title", ""), detail="Dashboard speech finished." if phase == "READY" else "Speech was interrupted by the operator.")
                return self.send_json({"result": result, "spoken": spoken, "voice_status": dict(last_tts_status)})
            if path == "/api/speak":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self.send_json({"error": "Paste a script first."}, 400)
                if len(text) > 12000:
                    return self.send_json({"error": "Speech scripts are limited to 12,000 characters."}, 400)
                core.publish_runtime("SPEAKING", answer=text, title="Saved script", detail="Robo is speaking a saved script.")
                try:
                    spoken = speak_and_wait(text)
                finally:
                    phase = "READY" if locals().get("spoken", True) else "INTERRUPTED"
                    core.publish_runtime(phase, answer=text, title="Saved script", detail="Script finished." if phase == "READY" else "Speech was interrupted by the operator.")
                core.add_history("script", text, text, "script-to-speech", "Speech script")
                return self.send_json({"ok": True, "spoken": spoken, "voice_status": dict(last_tts_status)})
            if path == "/api/history/clear":
                core.clear_history()
                return self.send_json({"ok": True, "history": []})
            if path == "/api/robot/start":
                mode = "ptt" if data.get("mode") == "ptt" else "voice"
                return self.send_json({"ok": True, "robot": start_robot(mode)})
            if path == "/api/robot/stop":
                core.request_speech_abort()
                core.publish_runtime("STOPPED", detail="Robot stopped from Robo Brain.")
                return self.send_json({"ok": True, "robot": stop_robot()})
            if path == "/api/robot/abort-speech":
                sequence = core.request_speech_abort()
                core.publish_runtime("INTERRUPTING", detail="Speech interrupted by the operator.")
                return self.send_json({"ok": True, "abort_seq": sequence})
            if path == "/api/scripts/save":
                name = str(data.get("name", "")).strip()[:120]
                text = str(data.get("text", "")).strip()
                script_id = str(data.get("id", "")).strip()
                if not name or not text:
                    return self.send_json({"error": "Give the saved script a name and some text."}, 400)
                if len(text) > 12000:
                    return self.send_json({"error": "Saved scripts are limited to 12,000 characters."}, 400)
                scripts = read_scripts()
                script = {"id": script_id or uuid.uuid4().hex, "name": name, "text": text,
                          "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
                index = next((i for i, item in enumerate(scripts) if item.get("id") == script["id"]), None)
                if index is None:
                    scripts.append(script)
                else:
                    scripts[index] = script
                core.atomic_json(SCRIPTS_PATH, scripts[-200:])
                return self.send_json({"ok": True, "scripts": read_scripts(), "script": script})
            if path == "/api/scripts/delete":
                script_id = str(data.get("id", ""))
                scripts = [item for item in read_scripts() if item.get("id") != script_id]
                core.atomic_json(SCRIPTS_PATH, scripts)
                return self.send_json({"ok": True, "scripts": scripts})
            if path == "/api/online/test":
                settings = core.get_settings()
                test_mode = data.get("mode", settings["mode"])
                section = "local_llm" if test_mode == "local" else "online"
                model_config = settings[section]
                key = model_config.get("api_key", "").strip()
                host = urlparse(model_config.get("base_url", "")).hostname or ""
                if not key and host.lower() not in ("localhost", "127.0.0.1", "::1"):
                    return self.send_json({"error": "Add an API key before testing this cloud connection."}, 400)
                if not model_config.get("base_url") or not model_config.get("model"):
                    return self.send_json({"error": "Set the model endpoint and model name first."}, 400)
                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Authorization"] = "Bearer " + key
                endpoint = urlparse(model_config["base_url"].rstrip("/"))
                is_ollama = test_mode == "local" and host.lower() in ("localhost", "127.0.0.1", "::1") and endpoint.port == 11434
                test_payload = {"model": model_config["model"], "messages": [{"role": "user", "content": "Reply briefly: Robo Brain connection is working."}], "stream": False}
                test_url = model_config["base_url"].rstrip("/") + "/chat/completions"
                if is_ollama:
                    test_url = f"{endpoint.scheme}://{endpoint.netloc}/api/chat"
                    test_payload.update({"think": False, "options": {"temperature": 0.2}})
                else:
                    test_payload["max_tokens"] = 1000
                req = Request(test_url,
                    data=json.dumps(test_payload).encode(),
                    method="POST", headers=headers)
                ssl_ctx = None
                try:
                    import certifi, ssl
                    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
                except Exception:
                    pass
                with urlopen(req, timeout=20, context=ssl_ctx) as response:
                    result = json.loads(response.read().decode("utf-8"))
                label = "Local model" if test_mode == "local" else "Cloud model"
                if is_ollama:
                    reply = result.get("message", {}).get("content", "")
                else:
                    reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not reply:
                    reply = "Connected successfully." 
                return self.send_json({"ok": True, "message": f"{label} connection is working: " + reply.strip()})
            return self.send_json({"error": "Not found"}, 404)
        except Exception as exc:
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Robo Brain is ready at http://127.0.0.1:8765")
    print("This control panel is local to this computer. Press Ctrl+C to stop it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_robot()
        server.server_close()

if __name__ == "__main__":
    main()
