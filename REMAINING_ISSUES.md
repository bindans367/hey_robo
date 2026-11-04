# REMAINING ISSUES & OPERATIONAL CONSIDERATIONS

---

## 1. Browser Extensions & Third-Party Console Warnings
During testing and browser console auditing, two common browser-level notices were evaluated:
- **`Search engine null is not supported`**:
  - **Origin**: Browser extension or browser default search-provider override (e.g., custom Omnibox / searchbar extensions).
  - **Impact on Robo**: None. The Robo codebase contains no search-provider APIs or browser engine extensions.
- **`Unchecked runtime.lastError: The message port closed before a response was received`**:
  - **Origin**: Chrome/Edge browser extensions (such as password managers, ad blockers, or translation tools) injecting content scripts into `localhost` tabs and closing background ports prematurely.
  - **Impact on Robo**: None. Robo does not use `chrome.runtime` extension messaging.

---

## 2. Operating System & Hardware Considerations
- **PyAudio / Microphone Device Indexing**:
  - On Windows, if USB audio peripherals or headsets are unplugged or reordered, Windows device IDs can shift. The system defaults to `-1` (Windows default communication input), which is the safest setting.
- **Speech Synthesis (TTS) Dependency**:
  - Windows SAPI (`provider: "system"`) operates 100% offline.
  - Indian English neural voices (`en-IN-NeerjaNeural`, `en-IN-AaravNeural`) connect to Microsoft Edge TTS online servers and require internet connectivity.

---

## 3. How to Run & Verify

1. **Start the Robo Brain Web Server**:
   ```powershell
   .\venv\Scripts\python.exe robo_brain.py
   ```
   Open `http://127.0.0.1:8765` in your browser.

2. **Start Interactive Eye Display**:
   Open `http://127.0.0.1:8765/eyes` in a separate tab or full-screen display.

3. **Start the Humanoid Robot Voice Assistant**:
   Click **"Start listening"** on the web dashboard, or run:
   ```powershell
   .\venv\Scripts\python.exe bot.py
   ```

4. **Run the Automated Test Suite**:
   ```powershell
   .\venv\Scripts\python.exe test_bot.py
   .\venv\Scripts\python.exe test_comprehensive.py
   ```
