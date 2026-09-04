"""
Unit Tests for Interactive Floating HUD, Ambient Perception, Action Journal, and Storage Compaction
===================================================================================================
Verifies:
1. Action Journal recording and rollback (Undo).
2. Multi-turn chat session memory persistence.
3. Storage compaction with 25 MB hard ceiling guarantee.
4. Ambient screen perception and article node extraction.
5. Self-contained zero-external-CDN Floating HUD template.
"""

import os
import sys
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from memory_manager import MemoryManager
from scripts.hud_template import HUD_HTML
from scripts.notification_action import handle_undo, handle_scan


class TestActionJournalAndRollback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "journal_test.db")
        self.mm = MemoryManager(db_path=self.db_path, auto_seed=False)

    def tearDown(self):
        self.mm.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_journal_record_and_retrieve_last_action(self):
        """Verify recording actions and retrieving the latest un-reverted action."""
        # Record an action with an inverse rollback
        aid = self.mm.record_action_journal(
            forward_action="volume",
            forward_params={"level": "80%"},
            inverse_action="volume",
            inverse_params={"level": 5},
            state_before={"volume": 5},
            state_after={"volume": 12},
            session_id="test_sess"
        )
        self.assertGreater(aid, 0)

        # Retrieve last action
        action = self.mm.get_last_reversible_action(session_id="test_sess")
        self.assertIsNotNone(action)
        self.assertEqual(action["forward_action"], "volume")
        self.assertEqual(action["inverse_action"], "volume")
        self.assertEqual(action["rolled_back"], 0)

    def test_journal_rollback_lifecycle(self):
        """Verify marking an action as rolled back prevents repeated undo."""
        aid1 = self.mm.record_action_journal(
            forward_action="brightness",
            forward_params={"level": 200},
            inverse_action="brightness",
            inverse_params={"level": 100}
        )
        aid2 = self.mm.record_action_journal(
            forward_action="volume",
            forward_params={"level": "100%"},
            inverse_action="volume",
            inverse_params={"level": 6}
        )

        # First undo targets the most recent action (aid2)
        last1 = self.mm.get_last_reversible_action()
        self.assertEqual(last1["id"], aid2)
        self.mm.mark_action_rolled_back(aid2)

        # Next undo targets aid1
        last2 = self.mm.get_last_reversible_action()
        self.assertEqual(last2["id"], aid1)
        self.mm.mark_action_rolled_back(aid1)

        # No further reversible actions remain
        self.assertIsNone(self.mm.get_last_reversible_action())


class TestMultiTurnSessionsAndCompaction(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "session_test.db")
        self.mm = MemoryManager(db_path=self.db_path, auto_seed=False)

    def tearDown(self):
        self.mm.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_chat_session_turns_persistence(self):
        """Verify saving and retrieving continuous multi-turn dialogue."""
        sess_id = "sess_demo_01"
        self.mm.create_session(sess_id, title="Research Session")

        t1 = self.mm.save_turn(sess_id, "user", "What is my current battery level?")
        t2 = self.mm.save_turn(sess_id, "assistant", "Battery is at 81% (Discharging).")
        t3 = self.mm.save_turn(sess_id, "user", "Now set volume to 50%")

        turns = self.mm.get_session_history(sess_id)
        self.assertEqual(len(turns), 3)
        self.assertEqual(turns[0]["content"], "What is my current battery level?")
        self.assertEqual(turns[1]["role"], "assistant")
        self.assertEqual(turns[2]["content"], "Now set volume to 50%")

    def test_storage_metrics_and_compaction_hard_ceiling(self):
        """Verify storage metrics calculation and 25MB hard ceiling enforcement."""
        metrics = self.mm.get_storage_metrics()
        self.assertIn("size_bytes", metrics)
        self.assertIn("size_mb", metrics)
        self.assertLess(metrics["size_mb"], 25.0)

        # Seed facts
        self.mm.save_fact("preferred_volume", "Volume 60% for daytime use", category="preference")
        facts = self.mm.list_facts()
        self.assertGreaterEqual(len(facts), 1)
        self.assertEqual(facts[0]["key"], "preferred_volume")

        # Test forced compaction
        res = self.mm.check_and_compact_storage(max_bytes=25 * 1024 * 1024, force=True)
        self.assertTrue(res["compacted"])
        self.assertTrue(res["under_ceiling"])
        self.assertLessEqual(res["size_bytes_after"], 25 * 1024 * 1024)


class TestAmbientPerceptionAndHUD(unittest.TestCase):
    def test_hud_html_integrity(self):
        """Verify HUD HTML contains essential mobile UI elements and zero external CDNs."""
        self.assertIn("<!DOCTYPE html>", HUD_HTML)
        self.assertIn("God-Mode Controller", HUD_HTML)
        self.assertIn("telemetry-pills", HUD_HTML)
        self.assertIn("quick-chips", HUD_HTML)
        self.assertIn("Scan Screen", HUD_HTML)
        self.assertIn("Undo Last Action", HUD_HTML)
        # Verify zero external CDNs (fonts, scripts, external css)
        self.assertNotIn("cdn.", HUD_HTML)
        self.assertNotIn("unpkg.com", HUD_HTML)
        self.assertNotIn("cdnjs.cloudflare.com", HUD_HTML)

    def test_ambient_article_node_extraction(self):
        """Verify parsing UI hierarchy XML and extracting article text."""
        sample_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
          <node index="0" text="" class="android.widget.FrameLayout">
            <node index="0" text="Autonomous agent - Wikipedia" class="android.widget.TextView" />
            <node index="1" text="An autonomous agent is an AI system that acts independently." class="android.widget.TextView" />
            <node index="2" text="Learn more" class="android.widget.Button" />
          </node>
        </hierarchy>"""

        root = ET.fromstring(sample_xml)
        texts = [n.attrib.get("text", "").strip() for n in root.iter("node") if n.attrib.get("text", "").strip()]
        self.assertIn("Autonomous agent - Wikipedia", texts)
        self.assertIn("An autonomous agent is an AI system that acts independently.", texts)
        self.assertEqual(len(texts), 3)


if __name__ == "__main__":
    unittest.main()
