import io
import json
import time
import unittest
import wave
import numpy as np
from urllib.request import Request, urlopen
from urllib.parse import quote

import robo_brain
import robo_brain_core as core
from matcher import matcher
import voice_engine


class TestVoiceEndpointsAndAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start RoboBrain server in a background thread for testing
        from http.server import ThreadingHTTPServer
        cls.server = ThreadingHTTPServer(("127.0.0.1", 8769), robo_brain.Handler)
        import threading
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_health_endpoint(self):
        with urlopen("http://127.0.0.1:8769/api/health", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "healthy")

    def test_02_tts_endpoint(self):
        url = "http://127.0.0.1:8769/api/tts?text=" + quote("Hello from Robo")
        with urlopen(url, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/mpeg")
            audio = resp.read()
            self.assertGreater(len(audio), 500)

    def test_03_transcribe_endpoint_silence(self):
        # Generate 0.5s of silent 16kHz WAV
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(8000, dtype=np.int16).tobytes())
        wav_bytes = buf.getvalue()

        req = Request(
            "http://127.0.0.1:8769/api/transcribe",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("text", ""), "")

    def test_04_ask_voice_endpoint_no_speech(self):
        # Silent audio should be cleanly detected as no speech without calling LLM
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(8000, dtype=np.int16).tobytes())
        wav_bytes = buf.getvalue()

        req = Request(
            "http://127.0.0.1:8769/api/ask-voice",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertFalse(data.get("ok"))
            self.assertEqual(data.get("reason"), "no_speech")

    def test_05_far_field_agc(self):
        # Quiet speech test: peak at 1000 should be amplified to near 4000
        raw = (np.sin(np.linspace(0, 100, 16000)) * 1000).astype(np.int16).tobytes()
        amplified = voice_engine._apply_far_field_agc(raw, 2)
        import audioop
        initial_peak = audioop.max(raw, 2)
        amplified_peak = audioop.max(amplified, 2)
        self.assertGreater(amplified_peak, initial_peak * 2)

    def test_06_gemini_conversational_response(self):
        # Ensure Gemini response is concise and under 60 words
        ans = core.answer_query("How can I join SIT college?", matcher, source="test")
        self.assertTrue(ans.get("matched"))
        word_count = len(ans.get("answer", "").split())
        self.assertLess(word_count, 70)
        self.assertNotIn("```", ans.get("answer", ""))


if __name__ == "__main__":
    unittest.main()
