"""
Unit Tests for On-Device Personal Knowledge Graph & Memory Manager
==================================================================
Verifies fuzzy contact resolution, routine storage, execution history logging,
RFC 2606 placeholder safety, and integration with master_agent.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure repository root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import memory_manager
from memory_manager import MemoryManager, normalize_query, strip_command_noise
import master_agent


class TestMemoryManagerCore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_memory.db")
        self.mm = MemoryManager(db_path=self.db_path, auto_seed=True)

    def tearDown(self):
        self.mm.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_schema_initialization_and_seeding(self):
        """Verify default tables and pre-seeded safe placeholders exist."""
        contacts = self.mm.list_contacts()
        self.assertGreaterEqual(len(contacts), 3)

        routines = self.mm.list_routines()
        self.assertGreaterEqual(len(routines), 2)

        # Verify zero real PII: RFC 2606 domain compliance and mock phone formats
        for c in contacts:
            email = c.get("email") or ""
            if email:
                self.assertTrue(
                    any(email.endswith(d) for d in ("example.com", "example.org", "example.net")),
                    f"Email {email} violates RFC 2606 domain guidelines"
                )

    def test_resolve_contact_maths_teacher(self):
        """Verify 'maths teacher' and natural language variations resolve to Lakhan Pal."""
        # 1. Exact relationship query
        res = self.mm.resolve_contact("maths teacher")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "Lakhan Pal")
        self.assertEqual(res["phone"], "+919999999999")

        # 2. Conversational query with stop words
        res_conv = self.mm.resolve_contact("call my maths teacher")
        self.assertIsNotNone(res_conv)
        self.assertEqual(res_conv["name"], "Lakhan Pal")
        self.assertEqual(res_conv["phone"], "+919999999999")

        # 3. Direct name query
        res_name = self.mm.resolve_contact("Lakhan")
        self.assertIsNotNone(res_name)
        self.assertEqual(res_name["name"], "Lakhan Pal")

        # 4. Partial token / Stemming
        res_stem = self.mm.resolve_contact("math teacher")
        self.assertIsNotNone(res_stem)
        self.assertEqual(res_stem["name"], "Lakhan Pal")

    def test_resolve_contact_doctor(self):
        """Verify doctor queries resolve to Alex Mercer."""
        res = self.mm.resolve_contact("doctor")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "Alex Mercer")
        self.assertEqual(res["phone"], "+15550199")

        res_conv = self.mm.resolve_contact("please reach out to my doctor")
        self.assertIsNotNone(res_conv)
        self.assertEqual(res_conv["name"], "Alex Mercer")

    def test_resolve_contact_notes_search(self):
        """Verify queries matching contact notes resolve properly."""
        res = self.mm.resolve_contact("calculus")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "Lakhan Pal")

    def test_resolve_contact_unknown_returns_none(self):
        """Verify queries with zero relevance return None."""
        res = self.mm.resolve_contact("unrelated interstellar spacecraft")
        self.assertIsNone(res)

    def test_contact_crud_lifecycle(self):
        """Verify adding, getting, listing, and deleting contacts."""
        cid = self.mm.add_contact(
            name="Jane Doe",
            relationship="Research Colleague",
            phone="+15550144",
            email="jane.doe@example.org",
            notes="AI robotics research partner"
        )
        self.assertIsInstance(cid, int)

        fetched = self.mm.get_contact(cid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Jane Doe")
        self.assertEqual(fetched["relationship"], "Research Colleague")

        resolved = self.mm.resolve_contact("robotics partner")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["id"], cid)

        deleted = self.mm.delete_contact(cid)
        self.assertTrue(deleted)
        self.assertIsNone(self.mm.get_contact(cid))

    def test_routine_storage_and_retrieval(self):
        """Verify adding routines and finding them via trigger phrases."""
        actions = [
            {"type": "volume", "level": "0%"},
            {"type": "brightness", "level": "20%"}
        ]
        rid = self.mm.add_routine(
            name="Night Focus",
            trigger="bedtime routine",
            actions_json=actions,
            context="Nightly shutdown"
        )
        self.assertIsInstance(rid, int)

        routine = self.mm.get_routine(rid)
        self.assertIsNotNone(routine)
        self.assertEqual(routine["name"], "Night Focus")
        parsed = json.loads(routine["actions_json"])
        self.assertEqual(len(parsed), 2)

        # Trigger search
        found = self.mm.find_routine("activate bedtime routine")
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], rid)

        # Default routine check
        morning = self.mm.find_routine("good morning")
        self.assertIsNotNone(morning)
        self.assertEqual(morning["name"], "Morning Briefing")

    def test_history_logging_and_retrieval(self):
        """Verify logging mission commands, status, outcome, and duration."""
        self.mm.clear_history()

        id1 = self.mm.record_history("set volume to 80%", status="success", duration_ms=124.5)
        id2 = self.mm.record_history("call maths teacher", status="success", duration_ms=250.0)
        id3 = self.mm.record_history("navigate home", status="failed", duration_ms=89.2)

        history = self.mm.get_recent_history(limit=5)
        self.assertEqual(len(history), 3)

        # Verify order is most recent first (descending by id)
        self.assertEqual(history[0]["instruction"], "navigate home")
        self.assertEqual(history[0]["status"], "failed")
        self.assertEqual(history[0]["outcome"], "failed")
        self.assertEqual(history[0]["command"], "navigate home")
        self.assertAlmostEqual(history[0]["duration_ms"], 89.2)

        self.assertEqual(history[1]["instruction"], "call maths teacher")
        self.assertEqual(history[2]["instruction"], "set volume to 80%")

        # Test limit
        history_limited = self.mm.get_recent_history(limit=2)
        self.assertEqual(len(history_limited), 2)


class TestMasterAgentMemoryIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "integration_memory.db")
        self.mm = MemoryManager(db_path=self.db_path, auto_seed=True)
        self.mock_device = MagicMock()
        self.mock_device.shell.return_value = ""

    def tearDown(self):
        self.mm.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_call_action_natural_language_contact_resolution(self):
        """Verify call_action('maths teacher') automatically resolves phone number via PKG."""
        with patch.object(master_agent, "memory_manager", self.mm):
            res = master_agent.call_action(self.mock_device, "maths teacher")
            # Should have resolved to Lakhan Pal's phone +919999999999
            self.mock_device.shell.assert_called_with('am start -a android.intent.action.CALL -d "tel:+919999999999"')
            self.assertIn("+919999999999", res)

    def test_call_action_conversational_phrase_resolution(self):
        """Verify call_action('my doctor') automatically resolves to Alex Mercer's phone."""
        with patch.object(master_agent, "memory_manager", self.mm):
            res = master_agent.call_action(self.mock_device, "my doctor")
            self.mock_device.shell.assert_called_with('am start -a android.intent.action.CALL -d "tel:+15550199"')
            self.assertIn("+15550199", res)

    def test_call_action_direct_number_passthrough(self):
        """Verify numeric phone number is dialed directly without lookup."""
        with patch.object(master_agent, "memory_manager", self.mm):
            res = master_agent.call_action(self.mock_device, "+15550123")
            self.mock_device.shell.assert_called_with('am start -a android.intent.action.CALL -d "tel:+15550123"')
            self.assertIn("+15550123", res)

    @patch("master_agent.Device")
    @patch("master_agent.verify_and_diagnose_step")
    def test_mission_execution_stored_routine_and_history_logging(self, mock_verify, mock_dev_cls):
        """Verify execute_autonomous_mission executes pre-stored routine and logs history."""
        mock_dev_cls.return_value = self.mock_device
        mock_verify.return_value = (True, "Verified")

        with patch.object(master_agent, "memory_manager", self.mm):
            master_agent.execute_autonomous_mission("good morning")

            # Verify history was recorded in memory manager
            history = self.mm.get_recent_history(limit=1)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["instruction"], "good morning")
            self.assertEqual(history[0]["status"], "success")
            self.assertGreaterEqual(history[0]["duration_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
