#!/usr/bin/env python3
"""
OpenDroid Multi-Provider Bridge
================================
High-performance OpenAI-compatible bridge for OpenDroid (com.opendroid.aiagent)
and Android Accessibility Service AI agents on Samsung Galaxy M56.

Features:
- Complete OpenAI v1 API compatibility:
  - GET /v1/models, GET /models, GET /v1/models/<id>
  - POST /v1/chat/completions, POST /chat/completions (streaming SSE & non-streaming)
  - Tool calling / function calling translation
  - Dynamic device telemetry injection (battery, foreground app, volume) into system context
- One-tap OpenDroid settings launcher (launch_opendroid_settings)
- CORS support for cross-origin web/app clients
"""

import os
import sys
import json
import re
import time
import uuid
import shutil
import subprocess
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    ThreadingHTTPServer = HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
try:
    from master_agent import query_llm_resilient, load_env
    load_env()
except ImportError:
    try:
        from autonomous_android_controller.master_agent import query_llm_resilient, load_env
        load_env()
    except ImportError:
        def query_llm_resilient(prompt_text, system_instruction):
            return f"Processed query: {prompt_text}"

HOST = os.environ.get("BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("BRIDGE_PORT", 4000))

MODELS_CATALOG = [
    {"id": "master-agent-resilient", "object": "model", "created": 1710000000, "owned_by": "autonomous-controller"},
    {"id": "smollm2-1.7b-instruct", "object": "model", "created": 1710000000, "owned_by": "offline-llama"},
    {"id": "flash-latest", "object": "model", "created": 1710000000, "owned_by": "ai-agent"},
    {"id": "groq-fast", "object": "model", "created": 1710000000, "owned_by": "groq"},
    {"id": "openrouter-free", "object": "model", "created": 1710000000, "owned_by": "openrouter"},
    {"id": "gpt-4o", "object": "model", "created": 1710000000, "owned_by": "openai-compatible"},
    {"id": "gpt-3.5-turbo", "object": "model", "created": 1710000000, "owned_by": "openai-compatible"}
]

# ─── Device Interaction & Telemetry ──────────────────────────────────────────

def resolve_adb_binary():
    env_bin = os.environ.get("ADB_BIN")
    if env_bin and (os.path.exists(env_bin) or shutil.which(env_bin)):
        return env_bin
    which_adb = shutil.which("adb")
    if which_adb:
        return which_adb
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        sdk_adb = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
        if os.path.exists(sdk_adb):
            return sdk_adb
    return "adb"

def run_shell(cmd, target=None):
    """Executes a shell command on device (via rish/sh on Android, or ADB on host)."""
    is_android = os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", "")
    if is_android:
        rish = "/system/bin/rish" if os.path.exists("/system/bin/rish") else "rish"
        has_rish = subprocess.run(f"command -v {rish}", shell=True, capture_output=True).returncode == 0
        if has_rish:
            full_cmd = f'{rish} -c {json.dumps(cmd)}'
            res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=5)
            return (res.stdout or "").strip()
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return (res.stdout or "").strip()

    adb = resolve_adb_binary()
    target = target or os.environ.get("ADB_TARGET", "")
    args = [adb]
    if target:
        args.extend(["-s", target])
    args.extend(["shell", cmd])
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return (res.stdout or "").strip()
    except Exception:
        return ""

def get_battery_level(target=None):
    """Retrieves current battery level percentage."""
    out = run_shell("dumpsys battery", target=target)
    m = re.search(r"\blevel:\s*(\d+)", out, re.IGNORECASE)
    if m:
        return f"{m.group(1)}%"
    return "Unknown"

def get_foreground_app(target=None):
    """Retrieves current focused package and activity."""
    out = run_shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'", target=target)
    m = re.search(r"mCurrentFocus=Window\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out)
    if not m:
        m = re.search(r"mFocusedApp=ActivityRecord\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out)
    if not m:
        out2 = run_shell("dumpsys activity activities 2>/dev/null | grep -E 'topResumedActivity|mResumedActivity'", target=target)
        m = re.search(r"(?:topResumedActivity|mResumedActivity)=ActivityRecord\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out2)
    if m:
        pkg, act = m.group(1), m.group(2)
        return f"{pkg} ({act})" if act else pkg
    return "Unknown"

def get_device_volume(target=None):
    """Retrieves current media stream volume."""
    out = run_shell("cmd media_session volume --stream 3 --get", target=target)
    m = re.search(r"volume is (\d+)", out)
    if m:
        return f"{m.group(1)}/15"
    return "Unknown"

def get_device_telemetry(target=None):
    """Collects battery level, foreground app, and volume."""
    try:
        battery = get_battery_level(target=target)
        fg_app = get_foreground_app(target=target)
        vol = get_device_volume(target=target)
        return {
            "battery": battery,
            "foreground_app": fg_app,
            "volume": vol
        }
    except Exception:
        return {
            "battery": "Unknown",
            "foreground_app": "Unknown",
            "volume": "Unknown"
        }

def format_telemetry_prompt(telemetry):
    """Formats telemetry dictionary into prompt injection block."""
    return (
        "[Active Device Telemetry]\n"
        f"- Battery Level: {telemetry.get('battery', 'Unknown')}\n"
        f"- Current Foreground App: {telemetry.get('foreground_app', 'Unknown')}\n"
        f"- Media Volume: {telemetry.get('volume', 'Unknown')}"
    )

def launch_opendroid_settings(target=None):
    """
    Launch OpenDroid configuration screen via direct intent:
    am start -n com.opendroid.aiagent/com.opendroid.ai.MainActivity
    """
    cmd = "am start -n com.opendroid.aiagent/com.opendroid.ai.MainActivity"
    out = run_shell(cmd, target=target)
    success = ("Starting: Intent" in out) or ("Error" not in out and bool(out))
    return {
        "success": success,
        "output": out,
        "component": "com.opendroid.aiagent/com.opendroid.ai.MainActivity"
    }

# ─── Tool Calling Translation ────────────────────────────────────────────────

def parse_tools_from_request(req):
    """Extract tool / function definitions from chat request."""
    tools = req.get("tools", [])
    if not tools and "functions" in req:
        tools = [{"type": "function", "function": f} for f in req.get("functions", [])]
    return tools

def build_tools_instruction(tools):
    """Constructs prompt section informing the LLM of available tool schemas."""
    if not tools:
        return ""
    tool_summaries = []
    for t in tools:
        if t.get("type") == "function" and "function" in t:
            fn = t["function"]
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            tool_summaries.append(f"Tool: {name}\nDescription: {desc}\nParameters Schema: {json.dumps(params)}")
    if not tool_summaries:
        return ""
    return (
        "\n\n[Available Tools / Function Calling]\n"
        + "\n\n".join(tool_summaries)
        + "\n\nIf you choose to invoke a tool, you MUST reply ONLY with a JSON object in one of the following formats without markdown commentary:\n"
        + '{"name": "<tool_name>", "arguments": {<args>}}\n'
        + "Do not include any conversational filler before or after the JSON."
    )

def extract_tool_call(res_text, tools=None):
    """
    Detects if the LLM output is a tool/function call and translates to OpenAI tool_call format.
    Returns (tool_name, tool_args_json_str) or None.
    """
    if not res_text or not isinstance(res_text, str):
        return None

    cleaned = res_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    valid_names = set()
    if tools:
        for t in tools:
            if t.get("type") == "function" and "function" in t:
                valid_names.add(t["function"].get("name"))

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # Format 1: {"name": ..., "arguments": ...}
            if "name" in data and ("arguments" in data or "parameters" in data or "args" in data):
                name = data["name"]
                args = data.get("arguments", data.get("parameters", data.get("args", {})))
                if not valid_names or name in valid_names:
                    return name, json.dumps(args) if isinstance(args, dict) else str(args)
            # Format 2: {"tool": ..., "parameters": ...}
            if "tool" in data and ("parameters" in data or "arguments" in data):
                name = data["tool"]
                args = data.get("parameters", data.get("arguments", {}))
                if not valid_names or name in valid_names:
                    return name, json.dumps(args) if isinstance(args, dict) else str(args)
            # Format 3: {"action": ..., "params": ...}
            if "action" in data and ("params" in data or "parameters" in data):
                name = data["action"]
                args = data.get("params", data.get("parameters", {}))
                if not valid_names or name in valid_names:
                    return name, json.dumps(args) if isinstance(args, dict) else str(args)
            # Format 4: {"tool_calls": [...]}
            if "tool_calls" in data and isinstance(data["tool_calls"], list) and len(data["tool_calls"]) > 0:
                first = data["tool_calls"][0]
                if isinstance(first, dict):
                    fn = first.get("function", first)
                    name = fn.get("name")
                    args = fn.get("arguments", {})
                    if name and (not valid_names or name in valid_names):
                        return name, json.dumps(args) if isinstance(args, dict) else str(args)
            # Format 5: Top-level tool name matching valid_names
            if valid_names:
                for vn in valid_names:
                    if vn in data and isinstance(data[vn], dict):
                        return vn, json.dumps(data[vn])
    except Exception:
        pass

    return None

# ─── Response Builders ────────────────────────────────────────────────────────

def build_chat_completion_response(req_id, model, content=None, tool_call=None, prompt_text=""):
    """Construct standard OpenAI non-streaming chat completion JSON payload."""
    choices = []
    if tool_call:
        tool_name, tool_args = tool_call
        tc_id = f"call_{uuid.uuid4().hex[:8]}"
        choices.append({
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }
                ]
            },
            "finish_reason": "tool_calls"
        })
    else:
        choices.append({
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content if content is not None else ""
            },
            "finish_reason": "stop"
        })

    prompt_tok = max(1, len(prompt_text) // 4)
    comp_tok = max(1, len(content or (tool_call[1] if tool_call else "")) // 4)

    return {
        "id": req_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": {
            "prompt_tokens": prompt_tok,
            "completion_tokens": comp_tok,
            "total_tokens": prompt_tok + comp_tok
        }
    }

def stream_sse_chunks(handler, req_id, model, content=None, tool_call=None):
    """Streams SSE events conforming to OpenAI v1 chunked SSE transfer-encoding protocol."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Transfer-Encoding", "chunked")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()

    def send_sse(data):
        payload = f"data: {json.dumps(data)}\n\n".encode("utf-8")
        chunk_header = f"{len(payload):X}\r\n".encode("ascii")
        handler.wfile.write(chunk_header + payload + b"\r\n")
        handler.wfile.flush()

    try:
        if tool_call:
            tool_name, tool_args = tool_call
            tc_id = f"call_{uuid.uuid4().hex[:8]}"
            # 1. Role delta
            send_sse({
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
            })
            # 2. Tool call delta
            send_sse({
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args
                            }
                        }]
                    },
                    "finish_reason": None
                }]
            })
            # 3. Finish reason
            send_sse({
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]
            })
        else:
            text = content or ""
            # 1. Role delta
            send_sse({
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
            })
            # 2. Content chunks
            chunks = re.findall(r"\S+|\s+", text) if text else [""]
            for ch in chunks:
                send_sse({
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}]
                })
            # 3. Stop finish
            send_sse({
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            })

        # Final DONE delimiter in SSE
        done_payload = b"data: [DONE]\n\n"
        chunk_header = f"{len(done_payload):X}\r\n".encode("ascii")
        handler.wfile.write(chunk_header + done_payload + b"\r\n")

        # End of chunked HTTP stream
        handler.wfile.write(b"0\r\n\r\n")
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        handler.close_connection = True

# ─── HTTP Request Handler ────────────────────────────────────────────────────

class OpenDroidBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        # Override to keep server output clean and predictable
        if os.environ.get("BRIDGE_DEBUG"):
            super().log_message(format, *args)

    def send_json_response(self, status_code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if not clean_path:
            clean_path = "/"

        if clean_path in ["/v1/models", "/models"]:
            self.send_json_response(200, {"object": "list", "data": MODELS_CATALOG})

        elif clean_path.startswith("/v1/models/") or clean_path.startswith("/models/"):
            model_id = clean_path.split("/")[-1]
            match = next((m for m in MODELS_CATALOG if m["id"] == model_id), None)
            if not match:
                match = {"id": model_id, "object": "model", "created": int(time.time()), "owned_by": "custom"}
            self.send_json_response(200, match)

        elif clean_path in ["/health", "/", "/v1/health"]:
            self.send_json_response(200, {
                "status": "active",
                "bridge": "opendroid-resilient-cluster",
                "version": "1.0.0"
            })

        elif clean_path in ["/telemetry", "/v1/telemetry"]:
            telemetry = get_device_telemetry()
            self.send_json_response(200, telemetry)

        else:
            self.send_json_response(404, {"error": {"message": f"Route not found: {self.path}", "type": "invalid_request_error"}})

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path in ["/v1/chat/completions", "/chat/completions"]:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body) if body.strip() else {}
                messages = req.get("messages", [])
                model_name = req.get("model", "master-agent-resilient")
                stream = bool(req.get("stream", False))
                tools = parse_tools_from_request(req)

                system_instruction = ""
                user_contents = []
                dialogue_history = []

                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if isinstance(content, list):
                        parts = []
                        for p in content:
                            if isinstance(p, dict) and p.get("type") == "text":
                                parts.append(p.get("text", ""))
                            elif isinstance(p, str):
                                parts.append(p)
                        content = " ".join(parts) if parts else str(content)
                    elif not isinstance(content, str):
                        content = str(content)

                    if role == "system":
                        if system_instruction:
                            system_instruction += "\n" + content
                        else:
                            system_instruction = content
                    elif role == "user":
                        user_contents.append(content)
                        dialogue_history.append(f"User: {content}")
                    elif role == "assistant":
                        dialogue_history.append(f"Assistant: {content}")

                if not system_instruction:
                    system_instruction = "You are OpenDroid autonomous agent."

                # Inject active device telemetry (battery level, current foreground app, volume)
                telemetry = get_device_telemetry()
                telemetry_block = format_telemetry_prompt(telemetry)
                system_instruction = f"{system_instruction}\n\n{telemetry_block}".strip()

                # Augment with tools if provided
                if tools:
                    tools_prompt = build_tools_instruction(tools)
                    if tools_prompt:
                        system_instruction = f"{system_instruction}\n{tools_prompt}".strip()

                if len(dialogue_history) > 1:
                    prompt_text = "\n".join(dialogue_history)
                elif user_contents:
                    prompt_text = user_contents[-1]
                else:
                    prompt_text = "Status check."

                # Execute LLM query
                res_text = query_llm_resilient(prompt_text, system_instruction)

                # Tool call translation check
                tool_call = extract_tool_call(res_text, tools)
                content = None if tool_call else res_text

                req_id = f"chatcmpl-{int(time.time())}-{uuid.uuid4().hex[:6]}"

                if stream:
                    stream_sse_chunks(self, req_id, model_name, content=content, tool_call=tool_call)
                else:
                    response_payload = build_chat_completion_response(
                        req_id, model_name, content=content, tool_call=tool_call, prompt_text=prompt_text
                    )
                    self.send_json_response(200, response_payload)

            except Exception as e:
                self.send_json_response(500, {
                    "error": {
                        "message": str(e),
                        "type": "bridge_error",
                        "code": 500
                    }
                })
        else:
            self.send_json_response(404, {"error": {"message": f"Route not found: {self.path}", "type": "invalid_request_error"}})

# ─── Server Lifecycle & CLI ──────────────────────────────────────────────────

def run_server(host=HOST, port=PORT):
    server = ThreadingHTTPServer((host, port), OpenDroidBridgeHandler)
    print(f"OpenDroid Bridge running on http://{host}:{port}/v1 (Endpoints: /v1/chat/completions, /v1/models)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down OpenDroid Bridge.")
        server.server_close()

def main():
    parser = argparse.ArgumentParser(description="OpenDroid OpenAI-Compatible Multi-Provider Bridge")
    parser.add_argument("--host", default=HOST, help="Host to bind server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=PORT, help="Port to bind server (default: 4000)")
    parser.add_argument("--launch-settings", "--launch", action="store_true", help="Launch OpenDroid app settings via intent")
    parser.add_argument("--telemetry", action="store_true", help="Print active device telemetry and exit")
    args = parser.parse_args()

    if args.launch_settings:
        res = launch_opendroid_settings()
        print(f"[OpenDroid Launcher] Result: {res}")
        return

    if args.telemetry:
        tel = get_device_telemetry()
        print("[Device Telemetry]:")
        for k, v in tel.items():
            print(f"  {k}: {v}")
        return

    run_server(args.host, args.port)

if __name__ == "__main__":
    main()
