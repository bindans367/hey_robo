"""
test_bot.py - Comprehensive Unit and Integration Test Suite
for SIT Humanoid Robot Offline Campus Assistant.

Run with:
    python test_bot.py
"""

import unittest
from normalizer import normalize_query
from matcher import matcher
import voice_engine


class TestNormalizer(unittest.TestCase):
    def test_acoustic_mistranscriptions(self):
        self.assertIn("sit", normalize_query("tell me about safety college"))
        self.assertIn("principal", normalize_query("who is the principle"))
        self.assertIn("tumakuru", normalize_query("where is tom cur"))
        self.assertIn("birla auditorium", normalize_query("bella auditorium location"))
        self.assertIn("halcyon", normalize_query("when is hall sean fest"))

    def test_department_acronyms(self):
        self.assertIn("cse", normalize_query("tell me about computer science and engineering"))
        self.assertIn("aiml", normalize_query("what is ai ml cutoff"))
        self.assertIn("ece", normalize_query("details of ec branch"))

    def test_facilities_and_personnel(self):
        self.assertIn("boys hostel", normalize_query("where is boy hostal"))
        self.assertIn("health centre", normalize_query("is there a doctor or medical clinic"))
        self.assertIn("dinesh", normalize_query("who is dr s v dinesh"))
        self.assertIn("swamiji", normalize_query("who is walking god"))


class TestMatcher(unittest.TestCase):
    def test_leadership_queries(self):
        res = matcher.search("who is the principal of sit")
        self.assertEqual(res["title"], "Principal of SIT")
        self.assertGreaterEqual(res["confidence"], 90.0)

        res2 = matcher.search("who is current president of math")
        self.assertEqual(res2["title"], "President - Sree Sree Siddalinga Swamiji")

        res3 = matcher.search("who is walking god trividha dasohi")
        self.assertEqual(res3["title"], "Founder - Dr. Sree Sree Shivakumara Swamigalu")

    def test_placements_and_academics(self):
        res = matcher.search("what is highest package in placement")
        self.assertEqual(res["title"], "Placement Packages and Statistics")

        res2 = matcher.search("what are the labs in cse department")
        self.assertEqual(res2["title"], "Computer Science and Engineering (CSE)")

    def test_facilities_and_regulations(self):
        res = matcher.search("where is bella auditor young")
        self.assertEqual(res["title"], "Birla Auditorium")

        res2 = matcher.search("tell me about boys hostel mess food")
        self.assertEqual(res2["title"], "Hostel Mess and Dining")

        res3 = matcher.search("what is minimum attendance required")
        self.assertEqual(res3["title"], "Attendance Requirement (85% Rule)")


class TestVoiceEngine(unittest.TestCase):
    def test_speech_cleanup(self):
        cleaned = voice_engine.clean_text_for_speech("SIT is accredited by NAAC and affiliated to VTU.")
        self.assertIn("S I T", cleaned)
        self.assertIn("N A A C", cleaned)
        self.assertIn("V T U", cleaned)


if __name__ == "__main__":
    unittest.main()
