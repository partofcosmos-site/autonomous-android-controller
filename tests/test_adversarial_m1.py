"""
Empirical Adversarial Stress Testing Suite for Milestone 1
===========================================================
Validates XML parsing, volume stream mapping, brightness control,
and key rotation under hostile/adversarial inputs, malformed data,
edge cases, and network failure cascades.
"""

import os
import sys
import re
import json
import unittest
from unittest.mock import MagicMock, patch
import requests

# Ensure repository root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import master_agent
import autoglm_agent
from rotate_keys import OpenRouterKeyRotator


# ═════════════════════════════════════════════════════════════════════════════
# 1. Adversarial XML Parser Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestXMLParserAdversarial(unittest.TestCase):
    """
    Stress tests UI hierarchy XML parser against empty strings, malformed syntax,
    unclosed tags, deeply nested trees, and missing/invalid bounds attributes.
    """

    def setUp(self):
        self.device = master_agent.Device(target="")
        self.autoglm_controller = autoglm_agent.DeviceController(target="")

    def test_empty_and_whitespace_xml(self):
        """Parser must return empty list [] without raising any exception on empty/whitespace input."""
        for empty_val in ["", "   ", "\n\t\n", None]:
            with patch.object(self.device, "shell", return_value="" if empty_val is None else empty_val):
                res = self.device.dump_screen()
                self.assertIsInstance(res, list)
                self.assertEqual(len(res), 0)

    def test_malformed_xml_syntax_errors(self):
        """Parser must survive completely malformed and corrupt XML strings."""
        malformed_inputs = [
            "<hierarchy> <<node broken>>",
            "<hierarchy><node text='foo' bounds='[0,0][100,100]' <broken",
            "Random text with <hierarchy but no valid closing tags or xml structure",
            "<hierarchy rotation=\"0\"><node text=\"broken\" bounds=\"[0,0][10,10]\"><node></hierarchy>",
            "<?xml version='1.0'?><hierarchy><node attr=unquoted_val bounds='[0,0][10,10]'/></hierarchy>",
            b"\x00\xff\xfe\xfd<hierarchy>binary garbage".decode("latin-1")
        ]
        for bad_xml in malformed_inputs:
            with patch.object(self.device, "shell", return_value=bad_xml):
                elements = self.device.dump_screen()
                self.assertIsInstance(elements, list)
                self.assertEqual(len(elements), 0)

    def test_unclosed_xml_tags(self):
        """Parser must survive truncated XML with unclosed tags."""
        unclosed_inputs = [
            "<hierarchy><node text='Incomplete'",
            "<hierarchy><node text='Missing End' bounds='[0,0][100,100]'>",
            "<hierarchy><node text='OK' bounds='[0,0][50,50]' clickable='true'><node text='nested'",
        ]
        for unclosed_xml in unclosed_inputs:
            with patch.object(self.device, "shell", return_value=unclosed_xml):
                elements = self.device.dump_screen()
                self.assertIsInstance(elements, list)
                self.assertEqual(len(elements), 0)

    def test_deeply_nested_xml_hierarchy(self):
        """Parser must traverse deeply nested XML trees (300+ levels) without RecursionError."""
        depth = 350
        open_tags = []
        close_tags = []
        for d in range(depth):
            if d == depth - 1:
                # Deepest node has text and bounds
                open_tags.append(
                    f'<node index="{d}" text="Deep Target" resource-id="deep_leaf" '
                    f'clickable="true" bounds="[100,200][300,400]">'
                )
            else:
                open_tags.append(f'<node index="{d}" text="" bounds="[0,0][1080,2400]">')
            close_tags.append("</node>")

        deep_xml = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n"
            "<hierarchy rotation=\"0\">\n"
            + "\n".join(open_tags)
            + "\n"
            + "\n".join(reversed(close_tags))
            + "\n</hierarchy>"
        )

        with patch.object(self.device, "shell", return_value=deep_xml):
            elements = self.device.dump_screen()
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0]["text"], "Deep Target")
            self.assertEqual(elements[0]["center"], [200, 300])

    def test_missing_and_invalid_bounds_attributes(self):
        """Nodes with missing, empty, or malformed bounds must be ignored safely without crash."""
        xml_bad_bounds = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" text="No Bounds Attribute" clickable="true" />
            <node index="1" text="Empty Bounds" bounds="" clickable="true" />
            <node index="2" text="Malformed Bounds 1" bounds="[invalid]" clickable="true" />
            <node index="3" text="Malformed Bounds 2" bounds="[10,20]" clickable="true" />
            <node index="4" text="Malformed Bounds 3" bounds="10,20,30,40" clickable="true" />
            <node index="5" text="Valid Node" bounds="[100,200][500,600]" clickable="true" />
        </hierarchy>"""

        with patch.object(self.device, "shell", return_value=xml_bad_bounds):
            elements = self.device.dump_screen()
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0]["text"], "Valid Node")
            self.assertEqual(elements[0]["center"], [300, 400])

    def test_extreme_and_inverted_bounds(self):
        """Parser must calculate center coordinates cleanly even for extreme or inverted bounds."""
        xml_bounds = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" text="Zero Dimensions" bounds="[500,500][500,500]" clickable="true" />
            <node index="1" text="Inverted Bounds" bounds="[600,800][200,400]" clickable="true" />
            <node index="2" text="Large Screen" bounds="[0,0][99999,99999]" clickable="true" />
        </hierarchy>"""

        with patch.object(self.device, "shell", return_value=xml_bounds):
            elements = self.device.dump_screen()
            self.assertEqual(len(elements), 3)
            # Zero-dimensions: (500+500)//2 = 500
            self.assertEqual(elements[0]["center"], [500, 500])
            # Inverted: (600+200)//2 = 400, (800+400)//2 = 600
            self.assertEqual(elements[1]["center"], [400, 600])
            # Large: (0+99999)//2 = 49999
            self.assertEqual(elements[2]["center"], [49999, 49999])

    def test_xml_with_special_characters_and_entities(self):
        """Parser must correctly decode XML entities and preserve unicode characters."""
        xml_entities = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" text="Save &amp; Exit &lt;New&gt; &quot;Now&quot;" content-desc="বাংলা ও हिंदी \u2705" bounds="[10,10][100,100]" clickable="true" />
        </hierarchy>"""

        with patch.object(self.device, "shell", return_value=xml_entities):
            elements = self.device.dump_screen()
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0]["text"], 'Save & Exit <New> "Now"')
            self.assertIn("বাংলা", elements[0]["desc"])
            self.assertIn("हिंदी", elements[0]["desc"])

    def test_autoglm_dump_ui_adversarial(self):
        """AutoGLM dump_ui must safely handle malformed XML, unclosed tags, and empty returns."""
        with patch.object(self.autoglm_controller, "shell", return_value="<hierarchy><unclosed broken"):
            elements = self.autoglm_controller.dump_ui()
            self.assertEqual(elements, [])


# ═════════════════════════════════════════════════════════════════════════════
# 2. Adversarial Volume Stream Mapping Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestVolumeStreamMappingAdversarial(unittest.TestCase):
    """
    Stress tests Samsung discrete 15-step volume stream mapping against edge cases:
    negative numbers, 0, 100, 105, keywords, non-numeric strings, and stream identifiers.
    """

    def setUp(self):
        self.device = MagicMock()
        self.device.shell.return_value = "volume is 8"

    def test_volume_negative_and_zero(self):
        """Volume of -1 and 0 must clamp cleanly to 0/15."""
        master_agent.set_volume_action(self.device, -1, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        master_agent.set_volume_action(self.device, 0, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        master_agent.set_volume_action(self.device, -999, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

    def test_volume_boundary_100_and_105(self):
        """Volume of 100 and 105 (exceeding 100%) must clamp cleanly to max 15/15."""
        # 100 -> 100 * 15 / 100 = 15
        master_agent.set_volume_action(self.device, 100, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

        # 105 -> round(105 * 15 / 100) = 16, clamped to 15
        master_agent.set_volume_action(self.device, 105, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

        # 999999 -> clamped to 15
        master_agent.set_volume_action(self.device, 999999, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

    def test_volume_keywords_mute_half_max(self):
        """Keyword string tokens ('mute', 'silence', 'zero', 'half', 'max', 'full') must map to exact discrete steps."""
        master_agent.set_volume_action(self.device, "mute", stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        master_agent.set_volume_action(self.device, "silence", stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 0")

        master_agent.set_volume_action(self.device, "half", stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 8")

        master_agent.set_volume_action(self.device, "max", stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

        master_agent.set_volume_action(self.device, "full", stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 15")

    def test_volume_non_numeric_and_invalid_strings(self):
        """Non-numeric garbage strings must not crash and fallback to safe default (12/15)."""
        invalid_tokens = ["foobar", "???", "loudness", "sound!"]
        for token in invalid_tokens:
            master_agent.set_volume_action(self.device, token, stream=3)
            self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 12")

    def test_volume_stream_type_mapping(self):
        """Stream names (ring, alarm, notif, system, music, other) must resolve to correct Android stream integer."""
        stream_expectations = [
            ("ring", 2),
            ("alarm", 4),
            ("notification", 5),
            ("notif", 5),
            ("system", 1),
            ("music", 3),
            ("unknown_stream", 3)
        ]
        for name, expected_stream in stream_expectations:
            master_agent.set_volume_action(self.device, "half", stream=name)
            self.device.shell.assert_called_with(f"cmd media_session volume --stream {expected_stream} --set 8")

    def test_volume_float_inputs(self):
        """Float inputs must be handled safely without TypeError."""
        master_agent.set_volume_action(self.device, 7.5, stream=3)
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 7")

        master_agent.set_volume_action(self.device, 50.0, stream=3)
        # 50.0 > 15 -> round(50.0 * 15 / 100) = 8
        self.device.shell.assert_called_with("cmd media_session volume --stream 3 --set 8")


# ═════════════════════════════════════════════════════════════════════════════
# 3. Adversarial Brightness Controller Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestBrightnessControllerAdversarial(unittest.TestCase):
    """
    Stress tests screen brightness controller against percentage boundaries
    ("0%", "50%", "100%", "255", negative numbers, invalid tokens).
    """

    def setUp(self):
        self.device = MagicMock()
        self.device.shell.return_value = "128"

    def test_brightness_percentage_boundaries(self):
        """Percentage boundary strings ('0%', '50%', '100%') must map to exact 0..255 steps."""
        # "0%" -> safe minimum 10 to prevent black screen lockup
        master_agent.set_brightness_action(self.device, "0%")
        self.device.shell.assert_called_with("settings put system screen_brightness 10")

        # "50%" -> exactly 128
        master_agent.set_brightness_action(self.device, "50%")
        self.device.shell.assert_called_with("settings put system screen_brightness 128")

        # "100%" -> exactly 255
        master_agent.set_brightness_action(self.device, "100%")
        self.device.shell.assert_called_with("settings put system screen_brightness 255")

    def test_brightness_raw_255_and_over_range(self):
        """Raw integer values and strings up to and exceeding 255 must clamp cleanly to 255."""
        master_agent.set_brightness_action(self.device, "255")
        self.device.shell.assert_called_with("settings put system screen_brightness 255")

        master_agent.set_brightness_action(self.device, 255)
        self.device.shell.assert_called_with("settings put system screen_brightness 255")

        master_agent.set_brightness_action(self.device, 500)
        self.device.shell.assert_called_with("settings put system screen_brightness 255")

    def test_brightness_negative_numbers(self):
        """Negative brightness inputs must clamp cleanly to safe lower bound (1..10) without crash."""
        master_agent.set_brightness_action(self.device, -50)
        # -50 <= 100 -> round(-50 * 255 / 100) = -128, clamped to max(1, min(255, -128)) = 1
        self.device.shell.assert_called_with("settings put system screen_brightness 1")

        master_agent.set_brightness_action(self.device, -1)
        self.device.shell.assert_called_with("settings put system screen_brightness 1")

    def test_brightness_invalid_tokens_and_none(self):
        """Invalid tokens, empty strings, and None must safely preserve current brightness."""
        self.device.shell.return_value = "128"
        for invalid_val in ["unknown", "gibberish", "", "!@#$", None]:
            master_agent.set_brightness_action(self.device, invalid_val)
            self.device.shell.assert_called_with("settings put system screen_brightness 128")

    def test_brightness_relative_keywords(self):
        """Relative adjustment keywords must shift brightness relative to current value."""
        self.device.shell.return_value = "100"
        master_agent.set_brightness_action(self.device, "brighter")
        self.device.shell.assert_called_with("settings put system screen_brightness 150")

        self.device.shell.return_value = "100"
        master_agent.set_brightness_action(self.device, "dim")
        self.device.shell.assert_called_with("settings put system screen_brightness 50")


# ═════════════════════════════════════════════════════════════════════════════
# 4. Adversarial Key Rotation & Cascading Failover Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestKeyRotationCascadeAdversarial(unittest.TestCase):
    """
    Stress tests API key rotation under simulated HTTP 429 / 402 / timeout cascades.
    Verifies that index wraps cleanly modulo N without IndexError or unbounded drift.
    """

    def test_rotator_index_wrapping_modulo(self):
        """Key rotator must cleanly loop indefinitely across N keys without IndexError."""
        test_keys = ["key-alpha", "key-beta", "key-gamma"]
        with patch.dict(os.environ, {"OR_KEY_1": test_keys[0], "OR_KEY_2": test_keys[1], "OR_KEY_3": test_keys[2]}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            self.assertEqual(len(rotator.keys), 3)

            # Test 100 consecutive rotations
            for i in range(100):
                expected_key = test_keys[(i + 1) % 3]
                next_key = rotator.rotate_key()
                self.assertEqual(next_key, expected_key)
                self.assertEqual(rotator.current_key, expected_key)
                self.assertLess(rotator.current_index, 3)
                self.assertGreaterEqual(rotator.current_index, 0)
                self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), expected_key)

    @patch("rotate_keys.time.sleep")
    @patch("rotate_keys.requests.post")
    def test_http_429_402_timeout_cascade_clean_wrap(self, mock_post, mock_sleep):
        """
        Simulate a grueling cascade:
        Call 1: 429 Rate Limit -> rotate
        Call 2: 402 Payment Required -> rotate
        Call 3: Timeout Exception -> rotate (wrapping back to key 1!)
        Call 4: 429 Rate Limit -> rotate
        Call 5: ConnectionError Exception -> rotate
        Call 6: 200 OK -> SUCCESS!
        """
        mock_429 = MagicMock(status_code=429)
        mock_402 = MagicMock(status_code=402)
        mock_200 = MagicMock(status_code=200)
        mock_200.json.return_value = {
            "choices": [{"message": {"content": "Cascade survived successfully!"}}]
        }

        mock_post.side_effect = [
            mock_429,
            mock_402,
            requests.exceptions.Timeout("Read timed out"),
            mock_429,
            requests.exceptions.ConnectionError("Connection reset"),
            mock_200
        ]

        test_keys = ["key-1", "key-2", "key-3"]
        with patch.dict(os.environ, {"OR_KEY_1": test_keys[0], "OR_KEY_2": test_keys[1], "OR_KEY_3": test_keys[2]}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            res = rotator.send_chat_completion(
                model="test/model",
                messages=[{"role": "user", "content": "ping"}],
                max_retries=10
            )
            self.assertEqual(res["choices"][0]["message"]["content"], "Cascade survived successfully!")
            self.assertEqual(mock_post.call_count, 6)
            # Verify rotator wrapped cleanly
            self.assertIn(rotator.current_key, test_keys)

    @patch("rotate_keys.time.sleep")
    @patch("rotate_keys.requests.post")
    def test_all_keys_exhausted_raises_runtime_error(self, mock_post, mock_sleep):
        """When retries are exhausted under continuous 429s, must raise RuntimeError cleanly."""
        mock_429 = MagicMock(status_code=429)
        mock_post.return_value = mock_429

        test_keys = ["key-A", "key-B"]
        with patch.dict(os.environ, {"OR_KEY_1": test_keys[0], "OR_KEY_2": test_keys[1]}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            with self.assertRaises(RuntimeError) as ctx:
                rotator.send_chat_completion(
                    model="test/model",
                    messages=[{"role": "user", "content": "ping"}],
                    max_retries=6
                )
            self.assertIn("exhausted or failed", str(ctx.exception))
            self.assertEqual(mock_post.call_count, 6)

    def test_single_key_pool_wrap(self):
        """Single-key pool must rotate cleanly without zero-division or index errors."""
        with patch.dict(os.environ, {"OR_KEY_1": "solo-key"}, clear=False):
            rotator = OpenRouterKeyRotator(key_prefix="OR_KEY_")
            self.assertEqual(len(rotator.keys), 1)
            for _ in range(5):
                key = rotator.rotate_key()
                self.assertEqual(key, "solo-key")
                self.assertEqual(rotator.current_index, 0)

    def test_empty_keys_raises_value_error(self):
        """Rotator with empty key pool must raise ValueError on rotate_key and chat completion."""
        rotator = OpenRouterKeyRotator(key_prefix="NON_EXISTENT_PREFIX_")
        rotator.keys = []
        with self.assertRaises(ValueError):
            rotator.rotate_key()
        with self.assertRaises(ValueError):
            rotator.send_chat_completion(model="test", messages=[])

    @patch("master_agent.requests.post")
    def test_master_agent_multi_provider_tier_failover(self, mock_post):
        """
        Tests query_llm_resilient in master_agent:
        Tier 1: Primary Flash fails with 429 across models.
        Tier 2: Groq fails with timeouts.
        Tier 3: OpenRouter succeeds on key 1.
        """
        def fake_post(url, *args, **kwargs):
            if "generativelanguage.googleapis.com" in url:
                # Fail Tier 1 with 429
                resp = MagicMock(status_code=429)
                return resp
            elif "api.groq.com" in url:
                # Fail Tier 2 with connection error
                raise requests.exceptions.ConnectionError("Groq offline")
            elif "openrouter.ai" in url:
                # Succeed Tier 3
                resp = MagicMock(status_code=200)
                resp.json.return_value = {
                    "choices": [{"message": {"content": json.dumps({"status": "Tier 3 Rescued"})}}]
                }
                return resp
            return MagicMock(status_code=500)

        mock_post.side_effect = fake_post

        with patch.object(master_agent, "PRIMARY_FLASH_KEYS", ["flash-key-1"]):
            with patch.object(master_agent, "GROQ_KEYS", ["groq-key-1"]):
                with patch.object(master_agent, "OPENROUTER_KEYS", ["openrouter-key-1"]):
                    result = master_agent.query_llm_resilient("test prompt", "system instructions")
                    parsed = json.loads(result)
                    self.assertEqual(parsed["status"], "Tier 3 Rescued")

    @patch("master_agent.requests.post")
    def test_master_agent_tier_0_local_offline_success(self, mock_post):
        """
        Tests Tier 0 local endpoint succeeds without invoking cloud providers.
        """
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"action": "tap", "params": {"x": 100, "y": 200}})}}]
        }
        mock_post.return_value = resp

        with patch.dict(os.environ, {"LOCAL_LLM_URL": "http://127.0.0.1:8080/v1/chat/completions"}):
            result = master_agent.query_llm_resilient("test local prompt", "system local")
            parsed = json.loads(result)
            self.assertEqual(parsed["action"], "tap")
            mock_post.assert_called_once()
            self.assertIn("127.0.0.1:8080", mock_post.call_args[0][0])


class TestNewIntentActionsAdversarial(unittest.TestCase):
    def setUp(self):
        self.mock_device = MagicMock()
        self.mock_device.shell.return_value = ""

    def test_call_action_formatting_and_edge_cases(self):
        # Formatted phone with parens, dashes, spaces
        master_agent.call_action(self.mock_device, "(555) 123-4567")
        self.mock_device.shell.assert_called_with('am start -a android.intent.action.CALL -d "tel:5551234567"')

        # None / empty input handled without crash
        res = master_agent.call_action(self.mock_device, "")
        self.assertIn("Call placed", res)

    def test_alarm_action_boundary_clamping(self):
        # Over boundary hours and minutes
        master_agent.alarm_action(self.mock_device, hour=99, minute=120, message="Over")
        self.mock_device.shell.assert_called_with(
            'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 23 --ei android.intent.extra.alarm.MINUTES 59 --es android.intent.extra.alarm.MESSAGE "Over" --ez android.intent.extra.alarm.SKIP_UI true'
        )

        # Negative boundaries clamped to 0
        master_agent.alarm_action(self.mock_device, hour=-5, minute=-30, message="Negative")
        self.mock_device.shell.assert_called_with(
            'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 0 --ei android.intent.extra.alarm.MINUTES 0 --es android.intent.extra.alarm.MESSAGE "Negative" --ez android.intent.extra.alarm.SKIP_UI true'
        )

        # Unparseable string defaults gracefully
        master_agent.alarm_action(self.mock_device, hour="invalid_time", minute=None, message=None)
        self.mock_device.shell.assert_called_with(
            'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 7 --ei android.intent.extra.alarm.MINUTES 0 --es android.intent.extra.alarm.MESSAGE "Alarm" --ez android.intent.extra.alarm.SKIP_UI true'
        )

    def test_mode_action_fallback(self):
        # Unknown mode fallback to normal
        res = master_agent.mode_action(self.mock_device, "hyper_drive_quantum_mode")
        self.mock_device.shell.assert_any_call("cmd media_session volume --stream 3 --set 9")
        self.mock_device.shell.assert_any_call("settings put system screen_brightness 128")
        self.mock_device.shell.assert_any_call("settings put global zen_mode 0")
        self.assertIn("normal", res.lower())

    def test_notifications_parsing_adversarial(self):
        # Empty string / None
        self.assertEqual(master_agent.parse_and_filter_notifications(""), [])
        self.assertEqual(master_agent.parse_and_filter_notifications(None), [])

        # Malformed garbage text
        garbage = "random memory dump 0xdeadbeef without notification structures"
        self.assertEqual(master_agent.parse_and_filter_notifications(garbage), [])

        # Notification with null / empty fields
        null_record = "NotificationRecord(0x1: pkg=android user=UserHandle{0} id=1: Notification())\nandroid.title=null\nandroid.text=null\ntickerText=null"
        self.assertEqual(master_agent.parse_and_filter_notifications(null_record), [])

    def test_search_action_adversarial(self):
        # Empty query
        self.assertEqual(master_agent.search_action(""), "No search query provided.")

        # No keys configured
        with patch.dict(os.environ, {"SERPER_API_KEY": "", "TAVILY_API_KEY": ""}, clear=True):
            with patch.object(master_agent, "SERPER_KEY", ""):
                with patch.object(master_agent, "TAVILY_KEY", ""):
                    res = master_agent.search_action("test query")
                    self.assertIn("Neither SERPER_API_KEY nor TAVILY_API_KEY is configured", res)

        # Both keys configured but both services throw exceptions
        with patch.dict(os.environ, {"SERPER_API_KEY": "k1", "TAVILY_API_KEY": "k2"}):
            with patch("master_agent.requests.post", side_effect=Exception("Network down")):
                res = master_agent.search_action("quantum entanglement")
                self.assertIn("No search results found", res)


if __name__ == "__main__":
    unittest.main()
