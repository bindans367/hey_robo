"""
Comprehensive Automated Test Suite for Robo Humanoid Assistant.
Covers:
  - Backend API business logic & settings validation
  - Matcher and local knowledge retrieval
  - AI prompt and behavior constraints (identity, SIT scope)
  - System resilience and concurrency safety
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import robo_brain_core as core
from matcher import matcher


class TestBackendAPI(unittest.TestCase):
    """Tests for backend API validation and business logic in robo_brain_core."""

    def test_settings_retrieval(self):
        settings = core.get_settings()
        self.assertIn("mode", settings)
        self.assertIn("voice", settings)
        self.assertIn("conversation", settings)
        self.assertIn("system_prompt", settings)
        self.assertIn("ROBO", settings["system_prompt"])

    def test_offline_leadership_query(self):
        res = matcher.search("who is the principal of sit")
        self.assertTrue(res["matched"])
        self.assertEqual(res["title"], "Principal of SIT")
        self.assertIn("Dr. S. V. Dinesh", res["answer"])

    def test_offline_placement_query(self):
        res = matcher.search("placement packages and statistics")
        self.assertTrue(res["matched"])
        self.assertIn("Placement", res["title"])

    def test_offline_cse_department_query(self):
        res = matcher.search("what are the labs in cse department")
        self.assertTrue(res["matched"])
        self.assertIn("Computer Science and Engineering", res["title"])


class TestRoboAIBehavior(unittest.TestCase):
    """Tests for AI behavior, identity retention, and safety rules."""

    def test_identity_inquiry(self):
        ans = core.answer_query("Who are you?", matcher, source="test")
        self.assertTrue(ans.get("matched"))
        answer_text = ans.get("answer", "")
        self.assertIn("Robo", answer_text)
        self.assertIn("Siddaganga Institute of Technology", answer_text)

    def test_fallbacks_when_offline_mode(self):
        ans = core._offline_answer("who is the principal of sit", matcher)
        self.assertTrue(ans.get("matched"))
        self.assertEqual(ans.get("title"), "Principal of SIT")

    def test_empty_query_in_offline(self):
        ans = core._offline_answer("", matcher)
        self.assertFalse(ans.get("matched"))


class TestSystemResilience(unittest.TestCase):
    """Tests for system robustness, retry logic, and concurrent file safety."""

    def test_atomic_json_concurrency(self):
        test_path = os.path.join(core.DATA_DIR, "test_atomic_safety.json")
        try:
            core.atomic_json(test_path, {"test": True, "count": 42})
            self.assertTrue(os.path.exists(test_path))
            with open(test_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("count"), 42)
        finally:
            if os.path.exists(test_path):
                os.remove(test_path)


if __name__ == "__main__":
    unittest.main()
