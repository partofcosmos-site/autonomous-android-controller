#!/usr/bin/env python3
"""
Unit tests for OpenDroid Multi-Provider Bridge (opendroid_bridge.py).
Verifies:
- Models listing endpoints (/v1/models and /models)
- Chat completions routing (non-streaming, multi-turn, system prompt)
- Device telemetry injection (battery, foreground app, volume)
- Tool calling / function calling translation (streaming & non-streaming)
- Chunked SSE streaming protocol (role delta, content chunks, finish_reason, [DONE])
- Settings launcher intent dispatch (launch_opendroid_settings)
- CORS preflight and error handling
"""

import os
import sys
import json
import time
import socket
import threading
import requests
import pytest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import opendroid_bridge
from opendroid_bridge import (
    OpenDroidBridgeHandler,
    get_battery_level,
    get_foreground_app,
    get_device_volume,
    get_device_telemetry,
    format_telemetry_prompt,
    launch_opendroid_settings,
    extract_tool_call,
    parse_tools_from_request,
    build_tools_instruction,
    build_chat_completion_response
)


@pytest.fixture(scope="module")
def bridge_server():
    """Starts a ThreadingHTTPServer on an ephemeral port for testing."""
    server = opendroid_bridge.ThreadingHTTPServer(("127.0.0.1", 0), OpenDroidBridgeHandler)
    host, port = server.server_address
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


class TestOpenDroidModelsEndpoint:
    def test_get_v1_models(self, bridge_server):
        resp = requests.get(f"{bridge_server}/v1/models", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "list"
        models = data.get("data", [])
        model_ids = [m["id"] for m in models]
        assert "master-agent-resilient" in model_ids
        assert "smollm2-1.7b-instruct" in model_ids
        assert "flash-latest" in model_ids

    def test_get_models_alias(self, bridge_server):
        resp = requests.get(f"{bridge_server}/models", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "list"
        assert len(data.get("data", [])) >= 3

    def test_get_single_model(self, bridge_server):
        resp = requests.get(f"{bridge_server}/v1/models/master-agent-resilient", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("id") == "master-agent-resilient"
        assert data.get("object") == "model"

    def test_health_check(self, bridge_server):
        resp = requests.get(f"{bridge_server}/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json().get("status") == "active"


class TestOpenDroidTelemetryAndPromptInjection:
    def test_telemetry_extraction_mocked(self):
        with patch("opendroid_bridge.run_shell") as mock_shell:
            def fake_shell(cmd, target=None):
                if "dumpsys battery" in cmd:
                    return "Current Battery Service state:\n  level: 88\n  scale: 100"
                elif "dumpsys window" in cmd:
                    return "mCurrentFocus=Window{123 u0 com.android.chrome/com.google.android.apps.chrome.Main}"
                elif "media_session volume" in cmd:
                    return "[V] volume is 9 in range [0..15]"
                return ""

            mock_shell.side_effect = fake_shell

            bat = get_battery_level()
            assert bat == "88%"

            app = get_foreground_app()
            assert "com.android.chrome" in app

            vol = get_device_volume()
            assert vol == "9/15"

            telemetry = get_device_telemetry()
            assert telemetry["battery"] == "88%"
            assert "com.android.chrome" in telemetry["foreground_app"]
            assert telemetry["volume"] == "9/15"

            prompt_block = format_telemetry_prompt(telemetry)
            assert "[Active Device Telemetry]" in prompt_block
            assert "Battery Level: 88%" in prompt_block
            assert "Current Foreground App: com.android.chrome" in prompt_block
            assert "Media Volume: 9/15" in prompt_block

    def test_telemetry_fallback_on_error(self):
        with patch("opendroid_bridge.run_shell", side_effect=Exception("ADB disconnected")):
            telemetry = get_device_telemetry()
            assert telemetry["battery"] == "Unknown"
            assert telemetry["foreground_app"] == "Unknown"
            assert telemetry["volume"] == "Unknown"


class TestOpenDroidChatCompletions:
    @patch("opendroid_bridge.get_device_telemetry")
    @patch("opendroid_bridge.query_llm_resilient")
    def test_chat_completion_non_streaming(self, mock_llm, mock_telemetry, bridge_server):
        mock_telemetry.return_value = {
            "battery": "79%",
            "foreground_app": "com.sec.android.app.camera",
            "volume": "5/15"
        }
        mock_llm.return_value = "Picture taken successfully."

        payload = {
            "model": "master-agent-resilient",
            "messages": [
                {"role": "system", "content": "You are a camera assistant."},
                {"role": "user", "content": "Capture the photo now."}
            ],
            "stream": False
        }

        resp = requests.post(f"{bridge_server}/v1/chat/completions", json=payload, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "chat.completion"
        assert data.get("model") == "master-agent-resilient"
        assert len(data.get("choices", [])) == 1
        choice = data["choices"][0]
        assert choice["message"]["role"] == "assistant"
        assert choice["message"]["content"] == "Picture taken successfully."
        assert choice["finish_reason"] == "stop"

        # Verify telemetry was injected into the system prompt passed to the LLM
        mock_llm.assert_called_once()
        prompt_arg, system_arg = mock_llm.call_args[0]
        assert "Capture the photo now." in prompt_arg
        assert "You are a camera assistant." in system_arg
        assert "[Active Device Telemetry]" in system_arg
        assert "Battery Level: 79%" in system_arg
        assert "Foreground App: com.sec.android.app.camera" in system_arg
        assert "Media Volume: 5/15" in system_arg

    @patch("opendroid_bridge.get_device_telemetry")
    @patch("opendroid_bridge.query_llm_resilient")
    def test_chat_completion_streaming_sse(self, mock_llm, mock_telemetry, bridge_server):
        mock_telemetry.return_value = {
            "battery": "80%",
            "foreground_app": "com.opendroid.aiagent",
            "volume": "7/15"
        }
        mock_llm.return_value = "Hello OpenDroid agent on Samsung Galaxy M56"

        payload = {
            "model": "master-agent-resilient",
            "messages": [
                {"role": "user", "content": "Say hello to OpenDroid"}
            ],
            "stream": True
        }

        resp = requests.post(f"{bridge_server}/v1/chat/completions", json=payload, stream=True, timeout=5)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")

        events = []
        for line in resp.iter_lines():
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if line_str.startswith("data: "):
                val = line_str[6:].strip()
                events.append(val)
                if val == "[DONE]":
                    break

        assert len(events) >= 3
        assert events[-1] == "[DONE]"

        # Parse chunks
        chunks = [json.loads(e) for e in events[:-1]]
        # First chunk has role delta
        assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"
        # Content chunks contain words
        combined_content = "".join(
            c["choices"][0]["delta"].get("content", "") for c in chunks if "content" in c["choices"][0]["delta"]
        )
        assert combined_content == "Hello OpenDroid agent on Samsung Galaxy M56"
        # Final chunk before [DONE] has finish_reason == 'stop'
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


class TestToolCallingTranslation:
    def test_extract_tool_call_formats(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open an application",
                    "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}}
                }
            }
        ]

        # Format 1: Standard {"name": ..., "arguments": ...}
        raw1 = '{"name": "open_app", "arguments": {"app_name": "YouTube"}}'
        tc1 = extract_tool_call(raw1, tools)
        assert tc1 is not None
        assert tc1[0] == "open_app"
        assert json.loads(tc1[1]) == {"app_name": "YouTube"}

        # Format 2: Markdown wrapped
        raw2 = '```json\n{"name": "open_app", "arguments": {"app_name": "Settings"}}\n```'
        tc2 = extract_tool_call(raw2, tools)
        assert tc2 is not None
        assert tc2[0] == "open_app"
        assert json.loads(tc2[1]) == {"app_name": "Settings"}

        # Format 3: Action format
        raw3 = '{"action": "open_app", "params": {"app_name": "Chrome"}}'
        tc3 = extract_tool_call(raw3, tools)
        assert tc3 is not None
        assert tc3[0] == "open_app"

        # Non-tool text
        raw4 = "Just a conversational reply with no tool call."
        assert extract_tool_call(raw4, tools) is None

    @patch("opendroid_bridge.get_device_telemetry")
    @patch("opendroid_bridge.query_llm_resilient")
    def test_tool_calling_non_streaming(self, mock_llm, mock_telemetry, bridge_server):
        mock_telemetry.return_value = {"battery": "90%", "foreground_app": "com.android.settings", "volume": "7/15"}
        mock_llm.return_value = '{"name": "tap", "arguments": {"x": 250, "y": 500}}'

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "tap",
                    "description": "Tap coordinate",
                    "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}
                }
            }
        ]

        payload = {
            "model": "master-agent-resilient",
            "messages": [{"role": "user", "content": "Tap on the Wi-Fi icon"}],
            "tools": tools,
            "stream": False
        }

        resp = requests.post(f"{bridge_server}/v1/chat/completions", json=payload, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        choice = data["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        assert choice["message"]["content"] is None
        assert len(choice["message"]["tool_calls"]) == 1
        tc = choice["message"]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "tap"
        assert json.loads(tc["function"]["arguments"]) == {"x": 250, "y": 500}

    @patch("opendroid_bridge.get_device_telemetry")
    @patch("opendroid_bridge.query_llm_resilient")
    def test_tool_calling_streaming_sse(self, mock_llm, mock_telemetry, bridge_server):
        mock_telemetry.return_value = {"battery": "90%", "foreground_app": "com.opendroid.aiagent", "volume": "7/15"}
        mock_llm.return_value = '{"name": "launch_app", "arguments": {"pkg": "com.sec.android.app.clockpackage"}}'

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "launch_app",
                    "description": "Launch app",
                    "parameters": {"type": "object", "properties": {"pkg": {"type": "string"}}}
                }
            }
        ]

        payload = {
            "model": "master-agent-resilient",
            "messages": [{"role": "user", "content": "Open the Clock"}],
            "tools": tools,
            "stream": True
        }
        resp = requests.post(f"{bridge_server}/v1/chat/completions", json=payload, stream=True, timeout=5)
        assert resp.status_code == 200

        events = []
        for line in resp.iter_lines():
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if line_str.startswith("data: "):
                val = line_str[6:].strip()
                events.append(val)
                if val == "[DONE]":
                    break

        assert events[-1] == "[DONE]"
        chunks = [json.loads(e) for e in events[:-1]]
        # Contains chunk with tool_calls
        tool_call_chunks = [c for c in chunks if "tool_calls" in c["choices"][0]["delta"]]
        assert len(tool_call_chunks) == 1
        fn = tool_call_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]
        assert fn["name"] == "launch_app"
        assert "com.sec.android.app.clockpackage" in fn["arguments"]

        # Final chunk finish_reason is tool_calls
        assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


class TestOpenDroidSettingsLauncher:
    @patch("opendroid_bridge.run_shell")
    def test_launch_opendroid_settings(self, mock_shell):
        mock_shell.return_value = "Starting: Intent { cmp=com.opendroid.aiagent/com.opendroid.ai.MainActivity }"
        res = launch_opendroid_settings()
        assert res["success"] is True
        assert res["component"] == "com.opendroid.aiagent/com.opendroid.ai.MainActivity"
        mock_shell.assert_called_once_with("am start -n com.opendroid.aiagent/com.opendroid.ai.MainActivity", target=None)


class TestCORSAndErrorHandling:
    def test_options_cors(self, bridge_server):
        resp = requests.options(f"{bridge_server}/v1/chat/completions", timeout=5)
        assert resp.status_code == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")

    def test_404_not_found(self, bridge_server):
        resp = requests.get(f"{bridge_server}/unknown_endpoint", timeout=5)
        assert resp.status_code == 404
        assert "invalid_request_error" in resp.text

    @patch("opendroid_bridge.query_llm_resilient", side_effect=RuntimeError("Provider offline"))
    def test_500_error_propagation(self, mock_llm, bridge_server):
        payload = {
            "model": "master-agent-resilient",
            "messages": [{"role": "user", "content": "Trigger failure"}]
        }
        resp = requests.post(f"{bridge_server}/v1/chat/completions", json=payload, timeout=5)
        assert resp.status_code == 500
        data = resp.json()
        assert "Provider offline" in data["error"]["message"]
