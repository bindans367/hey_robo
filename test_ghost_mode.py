import json
import time
import unittest
from urllib.request import urlopen

import robo_brain
import robo_brain_core as core
from matcher import matcher
import voice_engine


class TestGhostMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        import threading
        cls.server = ThreadingHTTPServer(("127.0.0.1", 8771), robo_brain.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_wake_beep_function(self):
        # Verify wake beep runs without raising exceptions
        try:
            voice_engine.play_wake_beep()
            beep_ok = True
        except Exception as e:
            beep_ok = False
        self.assertTrue(beep_ok)

    def test_02_wake_beep_endpoint(self):
        with urlopen("http://127.0.0.1:8771/api/wake-beep", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/wav")
            audio = resp.read()
            self.assertGreater(len(audio), 1000)

    def test_03_tts_self_echo_suppression(self):
        # Verify is_tts_active suppresses wake word during and right after speech
        voice_engine._tts_is_speaking = True
        self.assertTrue(voice_engine.is_tts_active())

        voice_engine._tts_is_speaking = False
        voice_engine._last_tts_end_time = time.time()
        # Immediately after TTS finished, cool-down buffer must still be active
        self.assertTrue(voice_engine.is_tts_active())

        # After 1.0s, cool-down expires
        time.sleep(0.9)
        self.assertFalse(voice_engine.is_tts_active())

    def test_04_sleep_runtime_state(self):
        state = core.publish_runtime("SLEEP", detail="Ghost Mode: Sleeping silently.")
        self.assertEqual(state.get("phase"), "SLEEP")
        runtime = core.get_runtime()
        self.assertEqual(runtime.get("phase"), "SLEEP")

    def test_05_ghost_cycle_simulation(self):
        # 1. Start in SLEEP
        core.publish_runtime("SLEEP", detail="Ghost Mode: Sleeping.")
        self.assertEqual(core.get_runtime().get("phase"), "SLEEP")

        # 2. Wake-word triggered -> beep -> LISTENING
        voice_engine.play_wake_beep()
        core.publish_runtime("LISTENING", detail="Awake! Listening...")
        self.assertEqual(core.get_runtime().get("phase"), "LISTENING")

        # 3. Question processed by Gemini -> SPEAKING
        query = "Where can I find the canteen in SIT?"
        ans = core.answer_query(query, matcher, source="ghost_test")
        core.publish_runtime("SPEAKING", transcript=query, answer=ans["answer"])
        self.assertEqual(core.get_runtime().get("phase"), "SPEAKING")
        self.assertGreater(len(ans["answer"]), 10)

        # 4. Auto-returns to SLEEP
        core.publish_runtime("SLEEP", detail="Ghost Mode: Sleeping silently. Say 'Hey Robo' to wake.")
        self.assertEqual(core.get_runtime().get("phase"), "SLEEP")


if __name__ == "__main__":
    unittest.main()
