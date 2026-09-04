"""
Unit and Mock Tests for Autonomous Android Controller Suite
============================================================
Tests master_agent.py, agent.py, autoglm_agent.py, and rotate_keys.py
using deterministic mocks for ADB, Shizuku, and LLM endpoints.
"""

import os
import sys
import json
import shutil
import subprocess
import unittest
from unittest.mock import MagicMock, patch

# Ensure repository root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import master_agent
import agent
import autoglm_agent
from rotate_keys import OpenRouterKeyRotator

SAMPLE_XML_HIERARCHY = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.android.settings" bounds="[0,0][1080,2340]">
    <node index="0" text="Settings" resource-id="com.android.settings:id/title" class="android.widget.TextView" package="com.android.settings" bounds="[100,150][400,220]" clickable="false" content-desc="" />
    <node index="1" text="Wi-Fi" resource-id="com.android.settings:id/wifi_pref" class="android.widget.TextView" package="com.android.settings" bounds="[80,300][1000,450]" clickable="true" content-desc="Wi-Fi settings" />
    <node index="2" text="Sound &amp; vibration" resource-id="com.android.settings:id/sound_pref" class="android.widget.TextView" package="com.android.settings" bounds="[80,500][1000,650]" clickable="true" content-desc="Volume and vibration options" />
  </node>
</hierarchy>"""


class TestMasterAgentHelpers(unittest.TestCase):
    def setUp(self):
        self.mock_device = MagicMock()
        self.mock_device.shell.return_value = ""

    def test_clean_json(self):
        fenced = "```json\n{\"task\": \"test\", \"step\": 1}\n```"
        cleaned = master_agent.clean_json(fenced)
        data = json.loads(cleaned)
        self.assertEqual(data["task"], "test")

        raw_text = "Here is the result: {\"status\": \"ok\"} Thanks!"
        cleaned2 = master_agent.clean_json(raw_text)
        data2 = json.loads(cleaned2)
        self.assertEqual(data2["status"], "ok")

    def test_volume_discrete_mapping(self):
        # Current volume mocked as 8
        self.mock_device.shell.return_value = "volume is 8"

        # Percentage strings
        master_agent.set_volume_action(self.mock_device, "100%", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

        master_agent.set_volume_action(self.mock_device, "0%", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        # Keywords: max, mute, half
        master_agent.set_volume_action(self.mock_device, "max", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

        master_agent.set_volume_action(self.mock_device, "mute", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        master_agent.set_volume_action(self.mock_device, "half", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 8")

        # Relative keywords: up, down
        master_agent.set_volume_action(self.mock_device, "increase volume", stream=3)
        self.mock_device.shell.assert_called_with("cmd media_session volume --stream 3 --set 12")

    def test_media_control_action(self):
        master_agent.control_media_action(self.mock_device, "play")
        self.mock_device.shell.assert_called_with("cmd media_session dispatch play")
        self.mock_device.key.assert_called_with(126)

        master_agent.control_media_action(self.mock_device, "pause")
        self.mock_device.shell.assert_called_with("cmd media_session dispatch pause")
        self.mock_device.key.assert_called_with(127)

        master_agent.control_media_action(self.mock_device, "next")
        self.mock_device.shell.assert_called_with("cmd media_session dispatch next")
        self.mock_device.key.assert_called_with(87)

    def test_brightness_action(self):
        self.mock_device.shell.return_value = "100"
        master_agent.set_brightness_action(self.mock_device, "max")
        self.mock_device.shell.assert_called_with("settings put system screen_brightness 255")

        master_agent.set_brightness_action(self.mock_device, "50%")
        self.mock_device.shell.assert_called_with("settings put system screen_brightness 128")

    def test_open_app_action(self):
        master_agent.open_app_action(self.mock_device, "youtube")
        self.mock_device.shell.assert_called_with("monkey -p app.revanced.android.youtube -c android.intent.category.LAUNCHER 1")

        master_agent.open_app_action(self.mock_device, "whatsapp")
        self.mock_device.shell.assert_called_with("monkey -p com.whatsapp.w4b -c android.intent.category.LAUNCHER 1")

    def test_call_action(self):
        res = master_agent.call_action(self.mock_device, "+19876543210")
        self.mock_device.shell.assert_called_with('am start -a android.intent.action.CALL -d "tel:+19876543210"')
        self.assertIn("+19876543210", res)

    def test_alarm_action(self):
        res = master_agent.alarm_action(self.mock_device, 7, 30, "Team Meeting")
        self.mock_device.shell.assert_called_with(
            'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 7 --ei android.intent.extra.alarm.MINUTES 30 --es android.intent.extra.alarm.MESSAGE "Team Meeting" --ez android.intent.extra.alarm.SKIP_UI true'
        )
        self.assertIn("07:30", res)

        # Test string parsing
        master_agent.alarm_action(self.mock_device, "08:45", message="Wakeup")
        self.mock_device.shell.assert_called_with(
            'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 8 --ei android.intent.extra.alarm.MINUTES 45 --es android.intent.extra.alarm.MESSAGE "Wakeup" --ez android.intent.extra.alarm.SKIP_UI true'
        )

    def test_navigation_action(self):
        res = master_agent.navigation_action(self.mock_device, "Times Square, New York")
        self.mock_device.shell.assert_called_with('am start -a android.intent.action.VIEW -d "google.navigation:q=Times Square, New York"')
        self.assertIn("Times Square", res)

    def test_mode_action(self):
        # Study mode: stream 3 vol 0, brightness 30% (76), zen_mode 1
        res = master_agent.mode_action(self.mock_device, "study")
        self.mock_device.shell.assert_any_call("cmd media_session volume --stream 3 --set 0")
        self.mock_device.shell.assert_any_call("settings put system screen_brightness 76")
        self.mock_device.shell.assert_any_call("settings put global zen_mode 1")
        self.assertIn("study", res.lower())

        # Outdoor mode: stream 3 vol 15, brightness 255
        self.mock_device.reset_mock()
        res = master_agent.mode_action(self.mock_device, "outdoor")
        self.mock_device.shell.assert_any_call("cmd media_session volume --stream 3 --set 15")
        self.mock_device.shell.assert_any_call("settings put system screen_brightness 255")
        self.assertIn("outdoor", res.lower())

        # Bedtime mode: stream 3 vol 0, brightness 10, zen_mode 1
        self.mock_device.reset_mock()
        res = master_agent.mode_action(self.mock_device, "bedtime")
        self.mock_device.shell.assert_any_call("cmd media_session volume --stream 3 --set 0")
        self.mock_device.shell.assert_any_call("settings put system screen_brightness 10")
        self.mock_device.shell.assert_any_call("settings put global zen_mode 1")
        self.assertIn("bedtime", res.lower())

        # Normal mode: stream 3 vol 9, brightness 128, zen_mode 0
        self.mock_device.reset_mock()
        res = master_agent.mode_action(self.mock_device, "normal")
        self.mock_device.shell.assert_any_call("cmd media_session volume --stream 3 --set 9")
        self.mock_device.shell.assert_any_call("settings put system screen_brightness 128")
        self.mock_device.shell.assert_any_call("settings put global zen_mode 0")
        self.assertIn("normal", res.lower())

    def test_notifications_action_filtering(self):
        sample_dumpsys = '''
        NotificationRecord(0x01: pkg=com.whatsapp.w4b user=UserHandle{0} id=1 importance=3 channel=messages: Notification(flags=0))
            android.title=String (Alice)
            android.text=String (Hey, are you free?)
        NotificationRecord(0x02: pkg=com.google.android.gms user=UserHandle{0} id=2 importance=3 channel=com.google.android.gms.notifications::SECURITY_ALERTS: Notification(flags=0))
            android.title=String (Security Alert)
            android.text=String (New sign-in detected)
        NotificationRecord(0x03: pkg=com.android.systemui user=UserHandle{0} id=3 tag=charging_state importance=1: Notification(flags=0))
            android.title=String (Charging)
            android.text=String (85% - 20 mins until full)
        NotificationRecord(0x04: pkg=com.google.android.apps.messaging user=UserHandle{0} id=4 importance=3 channel=sms: Notification(flags=0))
            android.title=String (Bank)
            android.text=String (Your verification code is 123456)
        '''
        self.mock_device.shell.return_value = sample_dumpsys
        filtered = master_agent.parse_and_filter_notifications(sample_dumpsys)
        self.assertEqual(len(filtered), 3)
        packages = [item["package"] for item in filtered]
        self.assertIn("com.whatsapp.w4b", packages)
        self.assertIn("com.google.android.gms", packages)
        self.assertIn("com.google.android.apps.messaging", packages)
        self.assertNotIn("com.android.systemui", packages)

        summary = master_agent.dump_notifications_action(self.mock_device)
        self.assertIn("Alice", summary)
        self.assertIn("Security Alert", summary)
        self.assertIn("123456", summary)

    @patch("master_agent.requests.post")
    def test_search_action_serper_primary(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "answerBox": {"answer": "Paris is the capital of France."}
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"SERPER_API_KEY": "fake_serper_key"}):
            ans = master_agent.search_action("capital of France")
            self.assertEqual(ans, "Paris is the capital of France.")
            mock_post.assert_called_once()
            self.assertIn("google.serper.dev", mock_post.call_args[0][0])

    @patch("master_agent.requests.post")
    def test_search_action_tavily_fallback(self, mock_post):
        def fake_search_post(url, *args, **kwargs):
            if "serper.dev" in url:
                raise Exception("Serper rate limit 429")
            elif "tavily.com" in url:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"answer": "Tavily answer: Python 3.12 released in 2023."}
                return resp
            return MagicMock(status_code=500)

        mock_post.side_effect = fake_search_post

        with patch.dict(os.environ, {"SERPER_API_KEY": "fake_serper", "TAVILY_API_KEY": "fake_tavily"}):
            ans = master_agent.search_action("Python 3.12 release date")
            self.assertEqual(ans, "Tavily answer: Python 3.12 released in 2023.")
            self.assertEqual(mock_post.call_count, 2)


class TestDeviceScreenDump(unittest.TestCase):
    def test_dump_screen_bounding_box_parsing(self):
        dev = master_agent.Device(target="")
        with patch.object(dev, "shell") as mock_shell:
            mock_shell.side_effect = ["", SAMPLE_XML_HIERARCHY]
            elements = dev.dump_screen()
            self.assertEqual(len(elements), 3)  # Settings, Wi-Fi, Sound & vibration

            wifi = elements[1]
            self.assertEqual(wifi["text"], "Wi-Fi")
            self.assertEqual(wifi["desc"], "Wi-Fi settings")
            self.assertTrue(wifi["clickable"])
            # Bounds [80,300][1000,450] -> Center: [(80+1000)//2, (300+450)//2] = [540, 375]
            self.assertEqual(wifi["center"], [540, 375])


class TestReActVerificationLoop(unittest.TestCase):
    @patch("master_agent.query_llm_resilient")
    def test_verify_and_diagnose_step_success(self, mock_llm):
        dev = MagicMock()
        dev.get_device_state.return_value = {
            "foreground_package": "com.android.settings",
            "foreground_activity": ".SettingsActivity",
            "media_volume": "8/15 (53%)",
            "screen_brightness": "128/255 (50%)",
            "elements": [{"text": "Sound", "desc": "", "clickable": True, "center": [500, 600]}]
        }
        mock_llm.return_value = json.dumps({
            "diagnosis": "Settings screen is visible and volume changed",
            "verified_success": True,
            "evidence": "Volume level verified at 8/15",
            "corrective_action": "none"
        })

        success, msg = master_agent.verify_and_diagnose_step(dev, "Set volume to 50%", "Volume set to 8/15")
        self.assertTrue(success)
        self.assertIn("Verified", msg)

    @patch("master_agent.query_llm_resilient")
    def test_verify_and_diagnose_step_corrective_tap(self, mock_llm):
        dev = MagicMock()
        dev.get_device_state.return_value = {
            "foreground_package": "com.android.settings",
            "foreground_activity": ".SettingsActivity",
            "media_volume": "8/15 (53%)",
            "screen_brightness": "128/255 (50%)",
            "elements": []
        }
        # First attempt returns blocker with corrective tap; second attempt returns success
        mock_llm.side_effect = [
            json.dumps({
                "diagnosis": "Dialog blocker detected",
                "verified_success": False,
                "evidence": "Dismiss button present",
                "corrective_action": "tap",
                "action_params": {"x": 500, "y": 900}
            }),
            json.dumps({
                "diagnosis": "Blocker dismissed and goal completed",
                "verified_success": True,
                "evidence": "Target activity active",
                "corrective_action": "none"
            })
        ]

        success, msg = master_agent.verify_and_diagnose_step(dev, "Launch app", "Launch intent sent", max_retries=2)
        dev.tap.assert_called_with(500, 900)
        self.assertTrue(success)


class TestAgentFastController(unittest.TestCase):
    def test_clean_json_text(self):
        fenced = "```json\n{\"type\": \"action\", \"command\": \"input keyevent 24\"}\n```"
        cleaned = agent.clean_json_text(fenced)
        data = json.loads(cleaned)
        self.assertEqual(data["type"], "action")
        self.assertEqual(data["command"], "input keyevent 24")

    @patch("agent.subprocess.run")
    def test_execute_command(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        with patch("agent.os.path.exists", return_value=False):
            with patch.dict(os.environ, {"PREFIX": ""}):
                agent.execute_command("input keyevent 24")
                self.assertTrue(mock_sub.called)


class TestAutoGLMAgent(unittest.TestCase):
    def test_device_controller_element_dump(self):
        controller = autoglm_agent.DeviceController(target="")
        with patch.object(controller, "shell") as mock_shell:
            mock_shell.side_effect = ["", SAMPLE_XML_HIERARCHY]
            elements = controller.dump_ui()
            self.assertEqual(len(elements), 3)
            self.assertEqual(elements[1]["text"], "Wi-Fi")

    @patch("autoglm_agent.query_planner")
    def test_run_autonomous_agent_flow(self, mock_planner):
        mock_planner.side_effect = [
            json.dumps({"thought": "Click Wi-Fi", "action": "tap", "x": 540, "y": 375, "done": False}),
            json.dumps({"thought": "Goal reached", "action": "done", "done": True})
        ]
        with patch("autoglm_agent.DeviceController.dump_ui", return_value=[{"text": "Wi-Fi", "center": [540, 375]}]):
            with patch("autoglm_agent.DeviceController.tap") as mock_tap:
                autoglm_agent.run_autonomous_agent("Open Wi-Fi", max_steps=3)
                mock_tap.assert_called_with(540, 375)


class TestKeyRotator(unittest.TestCase):
    def test_key_rotation_mechanics(self):
        with patch.dict(os.environ, {"OR_KEY_1": "key-one", "OR_KEY_2": "key-two"}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            self.assertEqual(rotator.current_key, "key-one")
            next_key = rotator.rotate_key()
            self.assertEqual(next_key, "key-two")
            self.assertEqual(rotator.current_key, "key-two")
            looped_key = rotator.rotate_key()
            self.assertEqual(looped_key, "key-one")

    @patch("rotate_keys.requests.post")
    def test_send_chat_completion_with_429_failover(self, mock_post):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"choices": [{"message": {"content": "Rotated successfully"}}]}

        mock_post.side_effect = [mock_resp_429, mock_resp_200]

        with patch.dict(os.environ, {"OR_KEY_1": "test-key-1", "OR_KEY_2": "test-key-2"}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            res = rotator.send_chat_completion(
                model="test/model",
                messages=[{"role": "user", "content": "ping"}],
                max_retries=3
            )
            self.assertEqual(res["choices"][0]["message"]["content"], "Rotated successfully")
            self.assertEqual(mock_post.call_count, 2)


class TestCLIEntrypoints(unittest.TestCase):
    """
    Subprocess regression test suite for CLI entrypoints and wrapper scripts.
    Validates that --help flag execution exits cleanly with code 0, displays usage,
    and never attempts unmocked LLM requests, ADB calls, or hangs on input prompts.
    """

    def test_master_agent_help_flag(self):
        """Verify master_agent.py --help exits with code 0 and displays usage without LLM calls."""
        for flag in ["--help", "-h", "help"]:
            cmd = [sys.executable, os.path.join(REPO_ROOT, "master_agent.py"), flag]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=REPO_ROOT,
                timeout=10,
            )
            self.assertEqual(
                res.returncode, 0,
                f"master_agent.py {flag} returned non-zero exit code {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}"
            )
            self.assertIn("Usage: python master_agent.py", res.stdout)
            self.assertNotIn("RuntimeError", res.stderr)
            self.assertNotIn("Traceback", res.stderr)
            self.assertNotIn("All 19 LLM keys", res.stderr)
            self.assertNotIn("Executing Mission", res.stdout)

    def test_agent_help_flag(self):
        """Verify agent.py --help exits with code 0 and displays usage without LLM queries."""
        for flag in ["--help", "-h", "help"]:
            cmd = [sys.executable, os.path.join(REPO_ROOT, "agent.py"), flag]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=REPO_ROOT,
                timeout=10,
            )
            self.assertEqual(
                res.returncode, 0,
                f"agent.py {flag} returned non-zero exit code {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}"
            )
            self.assertIn("Usage: python agent.py", res.stdout)
            self.assertNotIn("[-] Execution Error", res.stdout)
            self.assertNotIn("[+] User:", res.stdout)
            self.assertNotIn("Traceback", res.stderr)

    def test_autoglm_help_flag(self):
        """Verify autoglm_agent.py --help exits with code 0 and displays usage without ADB calls."""
        for flag in ["--help", "-h", "help"]:
            cmd = [sys.executable, os.path.join(REPO_ROOT, "autoglm_agent.py"), flag]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=REPO_ROOT,
                timeout=10,
            )
            self.assertEqual(
                res.returncode, 0,
                f"autoglm_agent.py {flag} returned non-zero exit code {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}"
            )
            self.assertIn("Usage: python autoglm_agent.py", res.stdout)
            self.assertNotIn("Autonomous Visual Task", res.stdout)
            self.assertNotIn("Traceback", res.stderr)
            self.assertNotIn("FileNotFoundError", res.stderr)

    def test_summon_agent_help_flag(self):
        """Verify bash summon_agent.sh --help exits with code 0 and displays usage."""
        bash_bin = shutil.which("bash")
        if os.name == "nt":
            git_bash = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
            if os.path.isfile(git_bash):
                bash_bin = git_bash
        if not bash_bin:
            self.skipTest("bash interpreter not found on system PATH")

        script_path = "./summon_agent.sh"
        for flag in ["--help", "-h", "help"]:
            res = subprocess.run(
                [bash_bin, script_path, flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=REPO_ROOT,
                timeout=10,
            )
            self.assertEqual(
                res.returncode, 0,
                f"bash summon_agent.sh {flag} returned non-zero exit code {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}"
            )
            self.assertIn("Usage: summon_agent.sh", res.stdout)
            self.assertNotIn("Traceback", res.stderr)
            self.assertNotIn("RuntimeError", res.stderr)
            self.assertNotIn("Executing Mission", res.stdout)

    def test_entrypoints_no_args(self):
        """Verify entrypoints invoked without args display usage and exit with code 0."""
        for script in ["master_agent.py", "agent.py", "autoglm_agent.py"]:
            cmd = [sys.executable, os.path.join(REPO_ROOT, script)]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=REPO_ROOT,
                timeout=10,
            )
            self.assertEqual(res.returncode, 0, f"{script} with no args returned {res.returncode}")
            self.assertIn("Usage:", res.stdout)


if __name__ == "__main__":
    unittest.main()

