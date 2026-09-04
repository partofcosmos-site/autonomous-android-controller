#!/usr/bin/env python3
"""
God-Mode Android Daemon (god_daemon.py)
=======================================
Autonomous headless background service daemon running via Shizuku (UID 2000 shell privilege)
or ADB shell on Samsung Galaxy M56 (SM-M566B).

Provides:
- Full OpenDroid gesture parity with native Shizuku / Shell superpowers:
  * tap(x, y)
  * swipe(x1, y1, x2, y2, duration)
  * type_text(text) [with clipboard broadcast + input text fallback]
  * key(code) [hardware keys, back, home, recents, power, volume]
  * expand_notifications() [cmd statusbar expand-notifications]
  * collapse_panels() [cmd statusbar collapse]
  * open_quick_settings() [cmd statusbar expand-settings]
  * take_screenshot(path) [screencap -p]
- Headless background HTTP server (REST API on port 5005)
- Asynchronous file-based IPC queue (/sdcard/agent/daemon_queue)
- Autonomous instruction execution without requiring an interactive Termux terminal session
- Zero external dependencies (uses standard Python library)
"""

import os
import sys
import re
import json
import time
import signal
import shutil
import socket
import argparse
import subprocess
import threading
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    ThreadingHTTPServer = HTTPServer

# ─── Path & Environment Resolution ───────────────────────────────────────────

def get_agent_dir():
    """Resolves the primary agent root storage directory."""
    if os.path.isdir("/sdcard/agent"):
        return "/sdcard/agent"
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(here) == "scripts":
        parent = os.path.dirname(here)
        if os.path.isdir(os.path.join(parent, "docs")):
            return parent
    return here

AGENT_DIR = get_agent_dir()
DEFAULT_PORT = int(os.environ.get("GOD_DAEMON_PORT", 5005))
DEFAULT_HOST = os.environ.get("GOD_DAEMON_HOST", "0.0.0.0")

PID_FILE = os.path.join(AGENT_DIR, "god_daemon.pid")
LOG_FILE = os.path.join(AGENT_DIR, "god_daemon.log")
QUEUE_DIR = os.path.join(AGENT_DIR, "daemon_queue")
SCREENSHOTS_DIR = os.path.join(AGENT_DIR, "screenshots")

# ─── Named Keycode Map ────────────────────────────────────────────────────────

KEY_MAP = {
    "HOME": 3,
    "BACK": 4,
    "CALL": 5,
    "ENDCALL": 6,
    "0": 7, "1": 8, "2": 9, "3": 10, "4": 11,
    "5": 12, "6": 13, "7": 14, "8": 15, "9": 16,
    "STAR": 17, "POUND": 18,
    "DPAD_UP": 19, "DPAD_DOWN": 20, "DPAD_LEFT": 21, "DPAD_RIGHT": 22, "DPAD_CENTER": 23,
    "VOLUME_UP": 24, "VOLUME_DOWN": 25,
    "POWER": 26, "CAMERA": 27, "CLEAR": 28,
    "A": 29, "B": 30, "C": 31, "D": 32, "E": 33,
    "TAB": 61, "SPACE": 62, "ENTER": 66, "DELETE": 67,
    "DEL": 67, "BACKSPACE": 67,
    "ESCAPE": 111, "ESC": 111,
    "APP_SWITCH": 187, "RECENTS": 187,
    "PASTE": 279
}

# ─── GodMode Controller ───────────────────────────────────────────────────────

class GodModeController:
    """
    Direct hardware and UI controller for Samsung Galaxy M56 using Shizuku
    (UID 2000 privileged shell) or Host ADB shell.
    """

    def __init__(self, target=None):
        self.target = target or os.environ.get("ADB_TARGET", "")
        self.is_android = os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", "")
        self.rish_path = "/system/bin/rish" if os.path.exists("/system/bin/rish") else "rish"
        self.has_rish = self._check_rish()
        self.adb_bin = self._resolve_adb_binary()
        self._cached_uid = None

    def _check_rish(self):
        if not self.is_android:
            return False
        try:
            res = subprocess.run(f"command -v {self.rish_path}", shell=True, capture_output=True, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    def _resolve_adb_binary(self):
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

    def run_shell(self, cmd, timeout=15):
        """
        Executes a shell command via Shizuku (rish) on Android or ADB on host.
        Returns tuple: (output_str, return_code)
        """
        if self.is_android:
            if self.has_rish:
                full_cmd = f'{self.rish_path} -c {json.dumps(cmd)}'
                try:
                    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
                    return (res.stdout or res.stderr or "").strip(), res.returncode
                except subprocess.TimeoutExpired:
                    return "Command timed out", -1
                except Exception as e:
                    return str(e), -1
            else:
                try:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
                    return (res.stdout or res.stderr or "").strip(), res.returncode
                except subprocess.TimeoutExpired:
                    return "Command timed out", -1
                except Exception as e:
                    return str(e), -1
        else:
            args = [self.adb_bin]
            if self.target:
                args.extend(["-s", self.target])
            args.extend(["shell", cmd])
            try:
                res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
                return (res.stdout or res.stderr or "").strip(), res.returncode
            except subprocess.TimeoutExpired:
                return "Command timed out", -1
            except Exception as e:
                return str(e), -1

    def get_uid(self):
        """Retrieves shell UID (e.g. 2000 for shell/Shizuku, 0 for root)."""
        if self._cached_uid is not None:
            return self._cached_uid
        out, code = self.run_shell("id -u")
        if code == 0 and out.isdigit():
            self._cached_uid = int(out)
            return self._cached_uid
        # Fallback inspection of id command
        out, code = self.run_shell("id")
        m = re.search(r"uid=(\d+)", out)
        if m:
            self._cached_uid = int(m.group(1))
            return self._cached_uid
        return 2000 if not self.is_android else 10000

    # ─── Full OpenDroid Gesture Parity (Shizuku Superpowers) ─────────────────

    def tap(self, x, y):
        """Native tap gesture via 'input tap x y'."""
        try:
            ix, iy = int(x), int(y)
        except (ValueError, TypeError):
            return {"action": "tap", "success": False, "error": f"Invalid coordinates: ({x}, {y})"}
        cmd = f"input tap {ix} {iy}"
        out, code = self.run_shell(cmd)
        return {
            "action": "tap",
            "x": ix,
            "y": iy,
            "success": code == 0,
            "output": out
        }

    def swipe(self, x1, y1, x2, y2, duration=300):
        """Native swipe gesture via 'input swipe x1 y1 x2 y2 duration'."""
        try:
            ix1, iy1, ix2, iy2 = int(x1), int(y1), int(x2), int(y2)
            idur = max(50, int(duration))
        except (ValueError, TypeError):
            return {"action": "swipe", "success": False, "error": f"Invalid swipe parameters: ({x1},{y1}) -> ({x2},{y2})"}
        cmd = f"input swipe {ix1} {iy1} {ix2} {iy2} {idur}"
        out, code = self.run_shell(cmd)
        return {
            "action": "swipe",
            "x1": ix1,
            "y1": iy1,
            "x2": ix2,
            "y2": iy2,
            "duration": idur,
            "success": code == 0,
            "output": out
        }

    def type_text(self, text, use_clipboard=True):
        """
        Types text via clipboard broadcast injection or escaped 'input text'.
        Handles special characters, spaces, and Unicode emojis reliably.
        """
        if not text:
            return {"action": "type_text", "text": "", "success": True}

        text_str = str(text)
        # 1. If clipboard broadcast is enabled and text has spaces or special chars
        if use_clipboard:
            # Broadcast to Clipper service if running
            escaped_clip = text_str.replace("'", "'\\''")
            clip_cmd = f"am broadcast -a clipper.set -e text '{escaped_clip}'"
            self.run_shell(clip_cmd)
            # Try paste keyevent
            paste_out, paste_code = self.run_shell("input keyevent 279")
            if paste_code == 0 and "Error" not in paste_out:
                return {
                    "action": "type_text",
                    "text": text_str,
                    "method": "clipboard",
                    "success": True,
                    "output": paste_out
                }

        # 2. Fallback to native 'input text' with space & quote escaping
        encoded = (
            text_str.replace("\\", "\\\\")
            .replace(" ", "%s")
            .replace("'", "\\'")
            .replace('"', '\\"')
            .replace("&", "\\&")
            .replace(";", "\\;")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        cmd = f"input text {encoded}"
        out, code = self.run_shell(cmd)
        return {
            "action": "type_text",
            "text": text_str,
            "method": "input_text",
            "success": code == 0,
            "output": out
        }

    def key(self, code):
        """Dispatches keyevent via 'input keyevent <code>'."""
        resolved_code = None
        key_name = str(code).upper()

        if isinstance(code, int):
            resolved_code = code
        elif str(code).isdigit():
            resolved_code = int(code)
        elif key_name.startswith("KEYCODE_") and key_name[8:] in KEY_MAP:
            resolved_code = KEY_MAP[key_name[8:]]
        elif key_name in KEY_MAP:
            resolved_code = KEY_MAP[key_name]
        else:
            # Direct pass-through if string keyevent name or number
            resolved_code = code

        cmd = f"input keyevent {resolved_code}"
        out, code_ret = self.run_shell(cmd)
        return {
            "action": "key",
            "code": resolved_code,
            "key_name": key_name,
            "success": code_ret == 0,
            "output": out
        }

    def expand_notifications(self):
        """Expands the Android notification shade."""
        cmd = "cmd statusbar expand-notifications"
        out, code = self.run_shell(cmd)
        return {
            "action": "expand_notifications",
            "success": code == 0,
            "output": out
        }

    def collapse_panels(self):
        """Collapses all expanded statusbar and notification panels."""
        cmd = "cmd statusbar collapse"
        out, code = self.run_shell(cmd)
        return {
            "action": "collapse_panels",
            "success": code == 0,
            "output": out
        }

    def open_quick_settings(self):
        """Expands Android Quick Settings panel."""
        cmd = "cmd statusbar expand-settings"
        out, code = self.run_shell(cmd)
        return {
            "action": "open_quick_settings",
            "success": code == 0,
            "output": out
        }

    def take_screenshot(self, path=None):
        """Captures on-screen display to PNG via 'screencap -p'."""
        if not path:
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
            filename = f"screen_{int(time.time())}.png"
            path = os.path.join(SCREENSHOTS_DIR, filename).replace("\\", "/")

        parent_dir = os.path.dirname(path).replace("\\", "/")
        if parent_dir:
            self.run_shell(f"mkdir -p '{parent_dir}'")

        cmd = f"screencap -p {path}"
        out, code = self.run_shell(cmd)
        file_exists = False
        size_bytes = 0

        # Check local path if on-device or pull via ADB if on host
        if self.is_android:
            if os.path.exists(path):
                file_exists = True
                size_bytes = os.path.getsize(path)
        else:
            # Check via adb
            chk, _ = self.run_shell(f"ls -l {path}")
            if path in chk:
                file_exists = True

        return {
            "action": "take_screenshot",
            "path": path,
            "success": code == 0 and (file_exists or code == 0),
            "size_bytes": size_bytes,
            "output": out
        }

    # ─── Superpower Telemetry & Inspections ───────────────────────────────────

    def get_foreground_app(self):
        """Inspects window manager for focused package and activity."""
        out, _ = self.run_shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'")
        m = re.search(r"mCurrentFocus=Window\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out)
        if not m:
            m = re.search(r"mFocusedApp=ActivityRecord\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out)
        if not m:
            out2, _ = self.run_shell("dumpsys activity activities 2>/dev/null | grep -E 'topResumedActivity|mResumedActivity'")
            m = re.search(r"(?:topResumedActivity|mResumedActivity)=ActivityRecord\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", out2)
        if m:
            pkg, act = m.group(1), m.group(2)
            return {"package": pkg, "activity": act, "formatted": f"{pkg} ({act})" if act else pkg}
        return {"package": "Unknown", "activity": "", "formatted": "Unknown"}

    def get_battery(self):
        """Retrieves device battery level and charging status."""
        out, _ = self.run_shell("dumpsys battery")
        level_m = re.search(r"\blevel:\s*(\d+)", out, re.IGNORECASE)
        status_m = re.search(r"\bstatus:\s*(\d+)", out, re.IGNORECASE)
        level = int(level_m.group(1)) if level_m else -1
        return {
            "level": level,
            "percentage": f"{level}%" if level >= 0 else "Unknown",
            "charging": status_m.group(1) == "2" if status_m else False
        }

    def get_volume(self):
        """Retrieves current media stream volume (stream 3)."""
        out, _ = self.run_shell("cmd media_session volume --stream 3 --get")
        m = re.search(r"volume is (\d+)", out)
        if m:
            vol = int(m.group(1))
            return {"volume": vol, "formatted": f"{vol}/15"}
        return {"volume": -1, "formatted": "Unknown"}

    def get_telemetry(self):
        """Aggregates real-time device telemetry for autonomous orchestration."""
        return {
            "uid": self.get_uid(),
            "privilege": "UID 2000 (Shell / Shizuku)" if self.get_uid() == 2000 else f"UID {self.get_uid()}",
            "foreground_app": self.get_foreground_app(),
            "battery": self.get_battery(),
            "volume": self.get_volume(),
            "platform": "Android" if self.is_android else "Host-ADB",
            "timestamp": time.time()
        }

    # ─── Autonomous Dispatcher ────────────────────────────────────────────────

    def dispatch(self, payload):
        """
        Executes an action dictionary or natural language instruction payload.
        Supported schemas:
        1. {"action": "tap", "params": {"x": 100, "y": 200}}
        2. {"action": "tap", "x": 100, "y": 200}
        3. {"command": "input tap 100 200"}
        4. {"instruction": "expand notifications"}
        """
        if not isinstance(payload, dict):
            return {"success": False, "error": "Payload must be a JSON object"}

        action = payload.get("action", "").lower()
        params = payload.get("params", {})
        if not params and not action:
            # Check if direct instruction or command
            if "instruction" in payload:
                return self.execute_instruction(payload["instruction"])
            if "command" in payload:
                out, code = self.run_shell(payload["command"])
                return {"action": "command", "command": payload["command"], "output": out, "success": code == 0}

        # Merge top-level params if not inside params dict
        p = dict(params)
        for k, v in payload.items():
            if k not in ("action", "params", "instruction"):
                p[k] = v

        if action == "tap":
            return self.tap(p.get("x", 0), p.get("y", 0))
        elif action == "swipe":
            return self.swipe(
                p.get("x1", 0), p.get("y1", 0),
                p.get("x2", 0), p.get("y2", 0),
                p.get("duration", 300)
            )
        elif action in ("type", "type_text"):
            return self.type_text(p.get("text", ""), p.get("use_clipboard", True))
        elif action == "key":
            return self.key(p.get("code", p.get("key", "BACK")))
        elif action in ("expand_notifications", "notifications_expand"):
            return self.expand_notifications()
        elif action in ("collapse_panels", "collapse"):
            return self.collapse_panels()
        elif action in ("open_quick_settings", "quick_settings"):
            return self.open_quick_settings()
        elif action in ("screenshot", "take_screenshot"):
            return self.take_screenshot(p.get("path"))
        elif action == "telemetry":
            return {"action": "telemetry", "success": True, "data": self.get_telemetry()}
        elif action == "shell":
            cmd = p.get("cmd", p.get("command", ""))
            out, code = self.run_shell(cmd)
            return {"action": "shell", "command": cmd, "output": out, "success": code == 0}
        elif action == "instruction":
            return self.execute_instruction(p.get("instruction", ""))
        else:
            return {"success": False, "error": f"Unknown action: '{action}'"}

    def execute_instruction(self, instruction):
        """
        Executes a natural language instruction without requiring interactive terminal.
        Resolves quick shortcut presets first, or defers to master_agent if available.
        """
        norm = (instruction or "").strip().lower()
        if not norm:
            return {"action": "instruction", "success": False, "error": "Empty instruction"}

        # Built-in quick shortcuts for zero-latency execution
        if "expand notification" in norm or "show notification" in norm or "open notification" in norm:
            res = self.expand_notifications()
            res["instruction"] = instruction
            return res

        if "collapse" in norm or "close notification" in norm or "hide notification" in norm:
            res = self.collapse_panels()
            res["instruction"] = instruction
            return res

        if "quick settings" in norm or "expand settings" in norm:
            res = self.open_quick_settings()
            res["instruction"] = instruction
            return res

        if "screenshot" in norm or "take screen" in norm or "capture screen" in norm:
            res = self.take_screenshot()
            res["instruction"] = instruction
            return res

        if norm in ("go home", "home", "home screen"):
            res = self.key("HOME")
            res["instruction"] = instruction
            return res

        if norm in ("go back", "back"):
            res = self.key("BACK")
            res["instruction"] = instruction
            return res

        if "study mode" in norm or "silent mode" in norm:
            self.run_shell("cmd media_session volume --stream 3 --set 0")
            self.run_shell("settings put system screen_brightness 50")
            return {"action": "preset", "preset": "study_mode", "success": True, "instruction": instruction}

        if "outdoor mode" in norm:
            self.run_shell("settings put system screen_brightness 255")
            self.run_shell("cmd media_session volume --stream 3 --set 15")
            return {"action": "preset", "preset": "outdoor_mode", "success": True, "instruction": instruction}

        # Try to dispatch to master_agent if available in environment
        try:
            sys.path.insert(0, AGENT_DIR)
            from master_agent import query_llm_resilient
            prompt = f"Convert this user instruction into a single Android shell command or action: {instruction}"
            system_prompt = (
                "You are an autonomous Android controller. Reply ONLY with the exact shell command to execute, "
                "such as: am start -a android.intent.action.VIEW -d <url>, or input tap x y. No markdown commentary."
            )
            cmd_plan = query_llm_resilient(prompt, system_prompt).strip()
            # Clean markdown codeblocks
            if cmd_plan.startswith("```"):
                cmd_plan = "\n".join([line for line in cmd_plan.splitlines() if not line.startswith("```")]).strip()
            out, code = self.run_shell(cmd_plan)
            return {
                "action": "master_agent_instruction",
                "instruction": instruction,
                "planned_command": cmd_plan,
                "output": out,
                "success": code == 0
            }
        except Exception as e:
            return {
                "action": "instruction",
                "instruction": instruction,
                "success": False,
                "error": f"Failed to dispatch instruction via agent: {str(e)}"
            }


# ─── HTTP REST Daemon Handler ────────────────────────────────────────────────

class GodDaemonHTTPHandler(BaseHTTPRequestHandler):
    """
    REST API request handler for headless daemon interactions.
    Provides standard endpoints:
      GET  /health
      GET  /status
      GET  /state
      GET  /screenshot
      POST /tap
      POST /swipe
      POST /type
      POST /key
      POST /notifications/expand
      POST /notifications/collapse
      POST /quick_settings
      POST /screenshot
      POST /action
      POST /execute
      POST /instruction
      POST /shell
    """
    controller = None
    start_time = time.time()

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status_code, data):
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        if path in ("/", "/health", "/status"):
            uptime = time.time() - self.start_time
            telemetry = self.controller.get_telemetry()
            self._send_json(200, {
                "status": "ok",
                "service": "god_daemon",
                "uid": telemetry["uid"],
                "privilege": telemetry["privilege"],
                "uptime_seconds": round(uptime, 1),
                "telemetry": telemetry,
                "endpoints": [
                    "GET  /health",
                    "GET  /state",
                    "GET  /screenshot",
                    "POST /tap",
                    "POST /swipe",
                    "POST /type",
                    "POST /key",
                    "POST /notifications/expand",
                    "POST /notifications/collapse",
                    "POST /quick_settings",
                    "POST /screenshot",
                    "POST /action",
                    "POST /instruction",
                    "POST /shell"
                ]
            })
            return

        if path in ("/state", "/telemetry"):
            self._send_json(200, self.controller.get_telemetry())
            return

        if path == "/screenshot":
            res = self.controller.take_screenshot()
            png_path = res.get("path")
            if png_path and os.path.exists(png_path):
                try:
                    with open(png_path, "rb") as f:
                        img_data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(img_data)))
                    self._send_cors()
                    self.end_headers()
                    self.wfile.write(img_data)
                    return
                except Exception as e:
                    self._send_json(500, {"success": False, "error": f"Failed reading screenshot: {e}"})
                    return
            self._send_json(500, {"success": False, "error": "Screenshot failed or file inaccessible", "details": res})
            return

        self._send_json(404, {"error": "Endpoint not found", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body.strip() else {}
        except Exception:
            self._send_json(400, {"error": "Invalid JSON payload in request body"})
            return

        # Explicit endpoint routing
        if path == "/tap":
            x = payload.get("x", 0)
            y = payload.get("y", 0)
            res = self.controller.tap(x, y)
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path == "/swipe":
            res = self.controller.swipe(
                payload.get("x1", 0), payload.get("y1", 0),
                payload.get("x2", 0), payload.get("y2", 0),
                payload.get("duration", 300)
            )
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path in ("/type", "/type_text"):
            text = payload.get("text", "")
            use_clip = payload.get("use_clipboard", True)
            res = self.controller.type_text(text, use_clip)
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path == "/key":
            code = payload.get("code", payload.get("key", "BACK"))
            res = self.controller.key(code)
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path in ("/notifications/expand", "/expand_notifications"):
            res = self.controller.expand_notifications()
            self._send_json(200 if res.get("success") else 500, res)
            return

        if path in ("/notifications/collapse", "/collapse_panels"):
            res = self.controller.collapse_panels()
            self._send_json(200 if res.get("success") else 500, res)
            return

        if path in ("/quick_settings", "/open_quick_settings"):
            res = self.controller.open_quick_settings()
            self._send_json(200 if res.get("success") else 500, res)
            return

        if path == "/screenshot":
            path_arg = payload.get("path")
            res = self.controller.take_screenshot(path_arg)
            self._send_json(200 if res.get("success") else 500, res)
            return

        if path in ("/action", "/execute"):
            res = self.controller.dispatch(payload)
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path == "/instruction":
            instruction = payload.get("instruction", "")
            res = self.controller.execute_instruction(instruction)
            self._send_json(200 if res.get("success") else 400, res)
            return

        if path == "/shell":
            cmd = payload.get("cmd", payload.get("command", ""))
            out, code = self.controller.run_shell(cmd)
            self._send_json(200, {"command": cmd, "output": out, "exit_code": code, "success": code == 0})
            return

        self._send_json(404, {"error": "Endpoint not found", "path": path})

    def log_message(self, format, *args):
        # Suppress verbose standard HTTP request logs to keep log file clean
        pass


# ─── File-Based IPC Queue Watcher ─────────────────────────────────────────────

class QueueWatcher(threading.Thread):
    """
    Monitors QUEUE_DIR for incoming command files.
    Allows zero-socket, non-interactive execution from shell scripts or Tasker.
    Writes <uuid>.result.json once processed.
    """

    def __init__(self, controller, queue_dir=QUEUE_DIR, poll_interval=1.0):
        super().__init__(daemon=True)
        self.controller = controller
        self.queue_dir = queue_dir
        self.poll_interval = poll_interval
        self._running = True
        os.makedirs(self.queue_dir, exist_ok=True)

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                if os.path.exists(self.queue_dir):
                    entries = sorted(os.listdir(self.queue_dir))
                    for fname in entries:
                        if fname.endswith(".json") and not fname.endswith(".result.json") and not fname.endswith(".tmp"):
                            fpath = os.path.join(self.queue_dir, fname)
                            try:
                                with open(fpath, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                res = self.controller.dispatch(data)
                                res_path = os.path.join(self.queue_dir, f"{fname}.result.json")
                                with open(res_path, "w", encoding="utf-8") as f:
                                    json.dump(res, f, indent=2)
                                os.remove(fpath)
                            except Exception as err:
                                err_res = {"success": False, "error": f"Malformed task {fname}: {err}"}
                                try:
                                    with open(os.path.join(self.queue_dir, f"{fname}.result.json"), "w") as f:
                                        json.dump(err_res, f)
                                    os.remove(fpath)
                                except Exception:
                                    pass
            except Exception:
                pass
            time.sleep(self.poll_interval)


# ─── Daemon Lifecycle & Process Management ────────────────────────────────────

def write_pid_file(pid_path=PID_FILE):
    try:
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"[-] Warning: Failed to write PID file: {e}")

def remove_pid_file(pid_path=PID_FILE):
    try:
        if os.path.exists(pid_path):
            os.remove(pid_path)
    except Exception:
        pass

def get_running_pid(pid_path=PID_FILE):
    if not os.path.exists(pid_path):
        return None
    try:
        with open(pid_path, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        # Check process liveness
        if os.name == "posix":
            os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None

def stop_daemon(pid_path=PID_FILE):
    pid = get_running_pid(pid_path)
    if not pid:
        print("[-] God-Mode daemon is not currently running.")
        return True
    print(f"[+] Stopping God-Mode daemon (PID {pid})...")
    try:
        if os.name == "posix":
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.2)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
        remove_pid_file(pid_path)
        print("[+] God-Mode daemon successfully stopped.")
        return True
    except Exception as e:
        print(f"[-] Error stopping daemon: {e}")
        return False

def check_status(host=DEFAULT_HOST, port=DEFAULT_PORT, pid_path=PID_FILE):
    pid = get_running_pid(pid_path)
    print("=" * 60)
    print("🤖 GOD-MODE BACKGROUND DAEMON STATUS")
    print("=" * 60)
    if pid:
        print(f"  Status:       RUNNING (PID: {pid})")
    else:
        print("  Status:       NOT RUNNING (no active PID file)")

    # Test HTTP health endpoint
    target_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{target_host}:{port}/health"
    try:
        import urllib.request
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"  HTTP Health:  ONLINE (http://{target_host}:{port})")
                print(f"  Privilege:    {data.get('privilege', 'Unknown')}")
                print(f"  Uptime:       {data.get('uptime_seconds', 0)}s")
                telemetry = data.get("telemetry", {})
                print(f"  Battery:      {telemetry.get('battery', {}).get('percentage', 'Unknown')}")
                print(f"  Foreground:   {telemetry.get('foreground_app', {}).get('formatted', 'Unknown')}")
                return True
    except Exception:
        print(f"  HTTP Health:  OFFLINE or unreachable at {url}")
    return pid is not None

def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT, daemon_mode=False):
    """Initializes and runs the God-Mode HTTP service and IPC Queue Watcher."""
    controller = GodModeController()
    GodDaemonHTTPHandler.controller = controller

    write_pid_file()
    queue_watcher = QueueWatcher(controller)
    queue_watcher.start()

    server = ThreadingHTTPServer((host, port), GodDaemonHTTPHandler)
    server.daemon_threads = True

    def signal_handler(signum, frame):
        print("\n[+] God-Mode daemon received shutdown signal. Exiting gracefully...")
        queue_watcher.stop()
        remove_pid_file()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception:
        pass

    uid = controller.get_uid()
    print("=" * 65)
    print(f"⚡ GOD-MODE DAEMON STARTED on {host}:{port} (PID: {os.getpid()})")
    print(f"⚡ Shell Privilege: UID {uid} {'(Shizuku / Shell Superpower)' if uid == 2000 else ''}")
    print(f"⚡ Storage Root:   {AGENT_DIR}")
    print(f"⚡ IPC Queue Dir:  {QUEUE_DIR}")
    print("=" * 65)
    sys.stdout.flush()

    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        queue_watcher.stop()
        remove_pid_file()


# ─── CLI Entrypoint ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="God-Mode Android Autonomous Background Daemon")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address to bind HTTP server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind HTTP server (default: 5005)")
    parser.add_argument("--daemon", action="store_true", help="Run as headless background daemon")
    parser.add_argument("--stop", action="store_true", help="Stop running God-Mode daemon")
    parser.add_argument("--status", action="store_true", help="Check daemon running status and health")
    parser.add_argument("--instruction", type=str, help="Execute a single autonomous instruction and exit")
    parser.add_argument("--action", type=str, help="Execute a single gesture action (e.g. tap, swipe, key)")
    parser.add_argument("--params", type=str, help="JSON string of parameters for --action")
    args = parser.parse_args()

    if args.stop:
        success = stop_daemon()
        sys.exit(0 if success else 1)

    if args.status:
        running = check_status(host=args.host, port=args.port)
        sys.exit(0 if running else 1)

    controller = GodModeController()

    if args.instruction:
        res = controller.execute_instruction(args.instruction)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("success") else 1)

    if args.action:
        p = {}
        if args.params:
            try:
                p = json.loads(args.params)
            except Exception as e:
                print(json.dumps({"success": False, "error": f"Invalid --params JSON: {e}"}))
                sys.exit(1)
        res = controller.dispatch({"action": args.action, "params": p})
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("success") else 1)

    # Start server
    run_server(host=args.host, port=args.port, daemon_mode=args.daemon)


if __name__ == "__main__":
    main()
