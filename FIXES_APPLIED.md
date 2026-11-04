# FIXES APPLIED — ROBO CODEBASE

---

### 1. `voice_engine.py` (STT Startup & Fallback)
- **Problem**: Attempted downloading `large-v3-turbo` over the network on unauthenticated Hugging Face requests, freezing process initialization indefinitely.
- **Fix**: Updated model candidate loop to look for cached local models first (`tiny.en`), using `local_files_only=True`. If unavailable or fails, gracefully falls back to Vosk Kaldi speech recognizer rather than blocking execution.

### 2. `robo_brain_core.py` (Windows File Locking & SSL Context)
- **Problem 1**: `PermissionError: [WinError 5]` caused by simultaneous file read/write operations during `os.replace` on `robo_runtime_state.json`.
  - **Fix**: Added a 5-attempt retry loop with exponential sleep in `atomic_json()` to handle Windows file locking collisions cleanly.
- **Problem 2**: Python `urllib.request` threw `[ASN1: NOT_ENOUGH_DATA]` SSL errors when contacting Google APIs due to Windows Certificate store quirks.
  - **Fix**: Incorporated `certifi.where()` CA bundle into `ssl.create_default_context()` for all outbound HTTPS requests.

### 3. `robo_brain.py` (API Endpoints & Error Handling)
- **Problem 1**: Missing `/api/health` monitoring endpoint.
  - **Fix**: Added `/api/health` returning 200 OK with server status and version information.
- **Problem 2**: In `/api/online/test`, `NameError: name 'Request' is not defined` occurred due to a missing import, and direct dict indexing threw `KeyError: 'content'`.
  - **Fix**: Imported `Request, urlopen` and added defensive `.get("choices", [{}])[0].get("message", {}).get("content")` handling.

### 4. `web/app.js` & `web/eyes.js` & `eye-site/eyes.js` (Polling & Console Errors)
- **Problem**: Fixed interval polling (`setInterval(..., 900)` and `setInterval(..., 400)`) fired overlapping requests and flooded browser consoles with `net::ERR_CONNECTION_REFUSED` whenever the backend was offline.
- **Fix**: Introduced `statusInFlight` / `eyesInFlight` lock flags and exponential backoff retry algorithms (backing off up to 8–10 seconds when unreachable, and resetting to 400ms–900ms upon reconnection).

### 5. `data/robo_settings.json` & `web/index.html` (AI Prompts & Configuration)
- **Prompt**: Embedded the complete 9-section master system prompt defining Robo's identity, communication style, campus scope, accuracy rules, and standard greetings into `data/robo_settings.json`.
- **UI**: Increased the textarea `maxlength` in `web/index.html` from `3000` to `12000` characters.
- **Online Model**: Configured `gemini-3.5-flash-lite` to ensure reliable response times and zero 503 rate-limit drops.
