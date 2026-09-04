#!/usr/bin/env python3
"""
Unit and Integration Tests for God-Mode Daemon (god_daemon.py)
Tests full OpenDroid gesture parity, Shizuku superpowers, HTTP endpoints,
and asynchronous IPC queue processing.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import threading
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

# Ensure autonomous-android-controller root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import god_daemon
from god_daemon import GodModeController, GodDaemonHTTPHandler, QueueWatcher


# ─── 1. Controller Gesture Parity Tests ────────────────────────────────────────

class TestGodModeGestures:
    """Validates the 8 core Shizuku superpowers and OpenDroid gesture parity."""

    @pytest.fixture(autouse=True)
    def setup_controller(self):
        self.controller = GodModeController()

    def test_tap_valid_coordinates(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.tap(540, 1200)
            mock_shell.assert_called_once_with("input tap 540 1200")
            assert res["action"] == "tap"
            assert res["success"] is True
            assert res["x"] == 540
            assert res["y"] == 1200

    def test_tap_invalid_coordinates(self):
        res = self.controller.tap("invalid", 100)
        assert res["success"] is False
        assert "Invalid coordinates" in res["error"]

    def test_swipe_valid(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.swipe(100, 200, 300, 800, 450)
            mock_shell.assert_called_once_with("input swipe 100 200 300 800 450")
            assert res["action"] == "swipe"
            assert res["success"] is True
            assert res["duration"] == 450

    def test_swipe_invalid_params(self):
        res = self.controller.swipe(None, 100, 200, 300)
        assert res["success"] is False
        assert "Invalid swipe parameters" in res["error"]

    def test_type_text_clipboard_success(self):
        def mock_run_shell(cmd, timeout=15):
            if "clipper.set" in cmd:
                return "Broadcast completed", 0
            if "input keyevent 279" in cmd:
                return "", 0
            return "", 0

        with patch.object(self.controller, "run_shell", side_effect=mock_run_shell):
            res = self.controller.type_text("Hello World! Special #1", use_clipboard=True)
            assert res["action"] == "type_text"
            assert res["success"] is True
            assert res["method"] == "clipboard"

    def test_type_text_input_text_fallback(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.type_text("Hello World", use_clipboard=False)
            mock_shell.assert_called_once_with("input text Hello%sWorld")
            assert res["action"] == "type_text"
            assert res["success"] is True
            assert res["method"] == "input_text"

    def test_type_text_empty(self):
        res = self.controller.type_text("")
        assert res["success"] is True
        assert res["text"] == ""

    def test_key_integer_code(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.key(4)
            mock_shell.assert_called_once_with("input keyevent 4")
            assert res["action"] == "key"
            assert res["code"] == 4
            assert res["success"] is True

    def test_key_named_mapping(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.key("HOME")
            mock_shell.assert_called_once_with("input keyevent 3")
            assert res["code"] == 3

        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.key("APP_SWITCH")
            mock_shell.assert_called_once_with("input keyevent 187")
            assert res["code"] == 187

    def test_expand_notifications(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.expand_notifications()
            mock_shell.assert_called_once_with("cmd statusbar expand-notifications")
            assert res["action"] == "expand_notifications"
            assert res["success"] is True

    def test_collapse_panels(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.collapse_panels()
            mock_shell.assert_called_once_with("cmd statusbar collapse")
            assert res["action"] == "collapse_panels"
            assert res["success"] is True

    def test_open_quick_settings(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.open_quick_settings()
            mock_shell.assert_called_once_with("cmd statusbar expand-settings")
            assert res["action"] == "open_quick_settings"
            assert res["success"] is True

    def test_take_screenshot(self, tmp_path):
        out_file = str(tmp_path / "test_shot.png")
        # Create dummy output file
        with open(out_file, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.take_screenshot(out_file)
            mock_shell.assert_any_call(f"screencap -p {out_file}")
            assert res["action"] == "take_screenshot"
            assert res["success"] is True
            assert res["path"] == out_file


# ─── 2. Telemetry and State Inspection Tests ──────────────────────────────────

class TestGodModeTelemetry:
    @pytest.fixture(autouse=True)
    def setup_controller(self):
        self.controller = GodModeController()

    def test_get_uid_shell_privileged(self):
        with patch.object(self.controller, "run_shell", return_value=("2000", 0)):
            self.controller._cached_uid = None
            uid = self.controller.get_uid()
            assert uid == 2000

    def test_get_foreground_app(self):
        dump_output = "mCurrentFocus=Window{123456 u0 com.whatsapp.w4b/com.whatsapp.HomeActivity}"
        with patch.object(self.controller, "run_shell", return_value=(dump_output, 0)):
            res = self.controller.get_foreground_app()
            assert res["package"] == "com.whatsapp.w4b"
            assert res["activity"] == "com.whatsapp.HomeActivity"
            assert "com.whatsapp.w4b" in res["formatted"]

    def test_get_battery(self):
        battery_out = "Current Battery Service state:\n  level: 85\n  status: 2"
        with patch.object(self.controller, "run_shell", return_value=(battery_out, 0)):
            res = self.controller.get_battery()
            assert res["level"] == 85
            assert res["percentage"] == "85%"
            assert res["charging"] is True

    def test_get_volume(self):
        vol_out = "volume is 10"
        with patch.object(self.controller, "run_shell", return_value=(vol_out, 0)):
            res = self.controller.get_volume()
            assert res["volume"] == 10
            assert res["formatted"] == "10/15"

    def test_get_telemetry_aggregation(self):
        with patch.object(self.controller, "get_uid", return_value=2000):
            with patch.object(self.controller, "get_battery", return_value={"level": 90, "percentage": "90%", "charging": False}):
                with patch.object(self.controller, "get_volume", return_value={"volume": 8, "formatted": "8/15"}):
                    with patch.object(self.controller, "get_foreground_app", return_value={"package": "com.termux", "formatted": "com.termux"}):
                        telemetry = self.controller.get_telemetry()
                        assert telemetry["uid"] == 2000
                        assert "UID 2000" in telemetry["privilege"]
                        assert telemetry["battery"]["level"] == 90
                        assert telemetry["volume"]["volume"] == 8
                        assert telemetry["foreground_app"]["package"] == "com.termux"


# ─── 3. Dispatcher and Autonomous Instruction Tests ───────────────────────────

class TestGodModeDispatcher:
    @pytest.fixture(autouse=True)
    def setup_controller(self):
        self.controller = GodModeController()

    def test_dispatch_tap(self):
        with patch.object(self.controller, "tap", return_value={"success": True, "action": "tap"}) as mock_tap:
            payload = {"action": "tap", "params": {"x": 100, "y": 200}}
            res = self.controller.dispatch(payload)
            mock_tap.assert_called_once_with(100, 200)
            assert res["success"] is True

    def test_dispatch_swipe(self):
        with patch.object(self.controller, "swipe", return_value={"success": True, "action": "swipe"}) as mock_swipe:
            payload = {"action": "swipe", "x1": 50, "y1": 50, "x2": 50, "y2": 500, "duration": 400}
            res = self.controller.dispatch(payload)
            mock_swipe.assert_called_once_with(50, 50, 50, 500, 400)
            assert res["success"] is True

    def test_dispatch_unknown_action(self):
        res = self.controller.dispatch({"action": "fly_to_moon"})
        assert res["success"] is False
        assert "Unknown action" in res["error"]

    def test_dispatch_invalid_type(self):
        res = self.controller.dispatch(["not a dict"])
        assert res["success"] is False
        assert "JSON object" in res["error"]

    def test_instruction_expand_notifications(self):
        with patch.object(self.controller, "expand_notifications", return_value={"success": True, "action": "expand_notifications"}) as mock_expand:
            res = self.controller.execute_instruction("expand notifications please")
            mock_expand.assert_called_once()
            assert res["success"] is True

    def test_instruction_collapse(self):
        with patch.object(self.controller, "collapse_panels", return_value={"success": True, "action": "collapse_panels"}) as mock_collapse:
            res = self.controller.execute_instruction("collapse notification shade")
            mock_collapse.assert_called_once()
            assert res["success"] is True

    def test_instruction_quick_settings(self):
        with patch.object(self.controller, "open_quick_settings", return_value={"success": True, "action": "open_quick_settings"}) as mock_qs:
            res = self.controller.execute_instruction("show quick settings")
            mock_qs.assert_called_once()
            assert res["success"] is True

    def test_instruction_presets(self):
        with patch.object(self.controller, "run_shell", return_value=("", 0)) as mock_shell:
            res = self.controller.execute_instruction("study mode")
            assert res["success"] is True
            assert res["preset"] == "study_mode"
            assert mock_shell.call_count >= 2


# ─── 4. Headless HTTP Server Endpoints Tests ──────────────────────────────────

class TestGodDaemonHTTPAPI:
    @classmethod
    def setup_class(cls):
        cls.controller = GodModeController()
        GodDaemonHTTPHandler.controller = cls.controller
        # Find an open port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        cls.port = sock.getsockname()[1]
        sock.close()

        cls.server = god_daemon.ThreadingHTTPServer(("127.0.0.1", cls.port), GodDaemonHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        # Verify server is listening
        for _ in range(20):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                    break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def teardown_class(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, payload):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_get_health(self):
        mock_tel = {"uid": 2000, "privilege": "UID 2000 (Shell / Shizuku)", "battery": {"level": 85}, "volume": {"level": 10}}
        with patch.object(self.controller, "get_telemetry", return_value=mock_tel):
            status, data = self._get("/health")
            assert status == 200
            assert data["status"] == "ok"
            assert data["service"] == "god_daemon"
            assert "endpoints" in data

    def test_get_state(self):
        mock_tel = {"uid": 2000, "privilege": "UID 2000 (Shell / Shizuku)", "battery": {"level": 85}, "volume": {"level": 10}}
        with patch.object(self.controller, "get_telemetry", return_value=mock_tel):
            status, data = self._get("/state")
            assert status == 200
            assert "uid" in data
            assert "battery" in data


    def test_post_tap(self):
        with patch.object(self.controller, "tap", return_value={"action": "tap", "success": True, "x": 100, "y": 200}):
            status, data = self._post("/tap", {"x": 100, "y": 200})
            assert status == 200
            assert data["success"] is True

    def test_post_swipe(self):
        with patch.object(self.controller, "swipe", return_value={"action": "swipe", "success": True}):
            status, data = self._post("/swipe", {"x1": 10, "y1": 20, "x2": 30, "y2": 40})
            assert status == 200
            assert data["success"] is True

    def test_post_type(self):
        with patch.object(self.controller, "type_text", return_value={"action": "type_text", "success": True, "text": "test"}):
            status, data = self._post("/type", {"text": "test"})
            assert status == 200
            assert data["success"] is True

    def test_post_key(self):
        with patch.object(self.controller, "key", return_value={"action": "key", "success": True, "code": 4}):
            status, data = self._post("/key", {"code": "BACK"})
            assert status == 200
            assert data["success"] is True

    def test_post_notifications_expand(self):
        with patch.object(self.controller, "expand_notifications", return_value={"action": "expand_notifications", "success": True}):
            status, data = self._post("/notifications/expand", {})
            assert status == 200
            assert data["success"] is True

    def test_post_notifications_collapse(self):
        with patch.object(self.controller, "collapse_panels", return_value={"action": "collapse_panels", "success": True}):
            status, data = self._post("/notifications/collapse", {})
            assert status == 200
            assert data["success"] is True

    def test_post_quick_settings(self):
        with patch.object(self.controller, "open_quick_settings", return_value={"action": "open_quick_settings", "success": True}):
            status, data = self._post("/quick_settings", {})
            assert status == 200
            assert data["success"] is True

    def test_post_instruction(self):
        with patch.object(self.controller, "execute_instruction", return_value={"action": "instruction", "success": True, "instruction": "study mode"}):
            status, data = self._post("/instruction", {"instruction": "study mode"})
            assert status == 200
            assert data["success"] is True

    def test_post_shell(self):
        with patch.object(self.controller, "run_shell", return_value=("mock_output", 0)):
            status, data = self._post("/shell", {"cmd": "echo test"})
            assert status == 200
            assert data["success"] is True
            assert data["output"] == "mock_output"

    def test_not_found(self):
        status, data = self._get("/non_existent_endpoint")
        assert status == 404
        assert "error" in data


# ─── 5. Asynchronous IPC Queue Watcher Tests ─────────────────────────────────

class TestQueueWatcher:
    def test_queue_watcher_processes_file(self, tmp_path):
        queue_dir = str(tmp_path / "daemon_queue")
        controller = GodModeController()
        watcher = QueueWatcher(controller, queue_dir=queue_dir, poll_interval=0.1)
        watcher.start()

        try:
            # Write a task JSON file
            task_file = os.path.join(queue_dir, "task1.json")
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump({"action": "tap", "params": {"x": 50, "y": 50}}, f)

            with patch.object(controller, "tap", return_value={"action": "tap", "success": True, "x": 50, "y": 50}):
                # Wait for watcher to pick up and process task
                result_file = os.path.join(queue_dir, "task1.json.result.json")
                for _ in range(25):
                    if os.path.exists(result_file) and not os.path.exists(task_file):
                        break
                    time.sleep(0.1)

                assert os.path.exists(result_file), "Expected result file to be created"
                assert not os.path.exists(task_file), "Expected task file to be consumed"

                with open(result_file, "r", encoding="utf-8") as rf:
                    res_data = json.load(rf)
                assert res_data["success"] is True
                assert res_data["action"] == "tap"
        finally:
            watcher.stop()
            watcher.join(timeout=2)


# ─── 6. Process Management & PID File Tests ───────────────────────────────────

class TestProcessManagement:
    def test_pid_lifecycle(self, tmp_path):
        pid_file = str(tmp_path / "test.pid")
        assert god_daemon.get_running_pid(pid_file) is None

        god_daemon.write_pid_file(pid_file)
        assert os.path.exists(pid_file)

        # In POSIX or Windows, reading the pid file gives current pid
        with open(pid_file, "r") as f:
            saved_pid = int(f.read().strip())
        assert saved_pid == os.getpid()

        god_daemon.remove_pid_file(pid_file)
        assert not os.path.exists(pid_file)
