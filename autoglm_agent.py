#!/usr/bin/env python3
"""
Autonomous Android Visual GUI Agent
===================================
Visual GUI agent with dynamic on-screen element grounding.
Powered by Open-Source Fast Vision-Language Models & Multi-Provider Fallback Pool.
Full rootless Android control via ADB / Shizuku (rish).
"""

import os
import sys
import json
import re
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
import requests

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip("'\"")

load_env()

PRIMARY_FLASH_KEYS = [os.environ.get(f"PRIMARY_FLASH_KEY_{i}", "") for i in range(1, 8)]
PRIMARY_FLASH_KEYS = [k for k in PRIMARY_FLASH_KEYS if k] or ([os.environ.get("PRIMARY_FLASH_API_KEY", "")] if os.environ.get("PRIMARY_FLASH_API_KEY") else [])

GROQ_KEYS = [os.environ.get(f"GROQ_API_KEY_{i}", "") for i in range(1, 6)]
GROQ_KEYS = [k for k in GROQ_KEYS if k] or ([os.environ.get("GROQ_API_KEY", "")] if os.environ.get("GROQ_API_KEY") else [])

OPENROUTER_KEYS = [os.environ.get(f"OR_KEY_{i}", "") for i in range(1, 8)]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k] or ([os.environ.get("OPENROUTER_API_KEY", "")] if os.environ.get("OPENROUTER_API_KEY") else [])

ADB_TARGET = os.environ.get("ADB_TARGET", "")
ADB_BIN = os.environ.get("ADB_BIN", shutil.which("adb") or "adb")

class DeviceController:
    def __init__(self, target=ADB_TARGET):
        self.target = target
        self.is_android = os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", "")
        self.rish_path = "/system/bin/rish" if os.path.exists("/system/bin/rish") else "rish"
        self.has_rish = subprocess.run(f"command -v {self.rish_path}", shell=True, capture_output=True).returncode == 0

    def shell(self, cmd):
        if self.is_android and self.has_rish:
            full_cmd = f'{self.rish_path} -c {json.dumps(cmd)}'
            res = subprocess.run(full_cmd, shell=True, capture_output=True, encoding="utf-8", errors="replace")
            return (res.stdout or "").strip()
        elif self.is_android:
            res = subprocess.run(cmd, shell=True, capture_output=True, encoding="utf-8", errors="replace")
            return (res.stdout or "").strip()
        else:
            target_args = ["-s", self.target] if self.target else []
            res = subprocess.run([ADB_BIN] + target_args + ["shell", cmd], capture_output=True, encoding="utf-8", errors="replace")
            return (res.stdout or "").strip()

    def tap(self, x, y):
        print(f"[👉 Action] Tap ({x}, {y})")
        self.shell(f"input tap {x} {y}")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        print(f"[👆 Action] Swipe ({x1}, {y1}) -> ({x2}, {y2})")
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def type_text(self, text):
        print(f"[⌨️ Action] Type: '{text}'")
        encoded = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.shell(f"input text {encoded}")

    def key(self, keycode):
        print(f"[🔘 Action] Keycode: {keycode}")
        self.shell(f"input keyevent {keycode}")

    def home(self):
        self.key(3)

    def back(self):
        self.key(4)

    def enter(self):
        self.key(66)

    def recents(self):
        self.key(187)

    def launch_app(self, package_name):
        print(f"[🚀 Action] Launch App: {package_name}")
        self.shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")

    def dump_ui(self):
        self.shell("uiautomator dump /data/local/tmp/window_dump.xml")
        xml_str = self.shell("toybox cat /data/local/tmp/window_dump.xml 2>/dev/null")
        elements = []
        if "<hierarchy" in xml_str:
            xml_clean = xml_str[xml_str.find("<hierarchy"):]
            try:
                root = ET.fromstring(xml_clean)
                for node in root.iter("node"):
                    text = node.attrib.get("text", "").strip()
                    desc = node.attrib.get("content-desc", "").strip()
                    bounds_str = node.attrib.get("bounds", "")
                    pkg = node.attrib.get("package", "")
                    clickable = node.attrib.get("clickable", "false") == "true"
                    res_id = node.attrib.get("resource-id", "")
                    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
                    if m and (text or desc or clickable):
                        x1, y1, x2, y2 = map(int, m.groups())
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        elements.append({
                            "text": text,
                            "desc": desc,
                            "id": res_id,
                            "pkg": pkg,
                            "clickable": clickable,
                            "center": [center_x, center_y]
                        })
            except Exception:
                pass
        return elements

SYSTEM_PROMPT = """You are the Autonomous Android Visual GUI Controller Agent.
You interact with an Android phone (Samsung Galaxy M56) by examining the current screen's interactive UI elements and deciding the next step to achieve the user's goal.
You natively understand requests in English, Bengali (বাংলা), and Hindi (हिंदी). Translate non-English requests into exact Android actions.

Given:
1. User Goal (may be in English, Bengali, or Hindi)
2. List of visible UI elements on current screen with center [x, y] coordinates and labels.
3. History of past actions.

Determine the NEXT action to perform. Output ONLY valid JSON:
{
  "thought": "<reasoning why this action is chosen>",
  "action": "tap" | "type" | "swipe" | "key" | "launch_app" | "intent" | "done",
  "x": <x coordinate if tap>,
  "y": <y coordinate if tap>,
  "text": "<text if type>",
  "package": "<package name if launch_app>",
  "intent_cmd": "<full shell intent if direct intent is faster>",
  "keycode": <number if key action>,
  "done": true | false
}

Rules:
- For WhatsApp message: Direct intent: `am start -p com.whatsapp.w4b -a android.intent.action.VIEW -d "https://api.whatsapp.com/send?phone=<phone>&text=<encoded_msg>"`
- For YouTube search / play: Direct intent: `am start -p app.revanced.android.youtube -a android.intent.action.VIEW -d "https://www.youtube.com/results?search_query=<encoded_query>"`
- If an element matching the goal is visible, tap its exact [x, y] center.
- When the goal is completed, set `"action": "done"`, `"done": true`.
"""

def query_planner(goal, elements, history):
    prompt = f"""User Goal: {goal}

Current Screen Elements:
{json.dumps(elements[:25], indent=2)}

Past Actions Taken:
{json.dumps(history, indent=2)}

Decide next action (JSON):"""

    # 1. Try Primary Flash Endpoints (7 independent keys)
    if PRIMARY_FLASH_KEYS:
        primary_models = [m.strip() for m in os.environ.get("PRIMARY_FLASH_MODELS", "flash-lite-latest,flash-latest,flash-preview").split(",") if m.strip()]
        for key in PRIMARY_FLASH_KEYS:
            for model in primary_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    payload = {
                        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
                    }
                    res = requests.post(url, json=payload, timeout=6)
                    if res.status_code == 200:
                        return res.json()["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    continue

    # 2. Try Groq (5 independent keys)
    if GROQ_KEYS:
        for key in GROQ_KEYS:
            for model in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "groq/compound-mini"]:
                try:
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=5)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"]
                except Exception:
                    continue

    # 3. Try OpenRouter (7 independent keys)
    if OPENROUTER_KEYS:
        for key in OPENROUTER_KEYS:
            for model in ["minimax/minimax-m3:free", "nvidia/nemotron-3.5-lightning:free", "z-ai/glm-5.2:free", "google/gemma-4-31b-it:free"]:
                try:
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1
                    }
                    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=8)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"]
                except Exception:
                    continue

    raise RuntimeError("All 19 LLM keys across Primary Flash, Groq, and OpenRouter failed or rate limited.")

def run_autonomous_agent(goal, max_steps=8):
    device = DeviceController()
    print(f"\n==========================================")
    print(f"🤖 Autonomous Visual Task: '{goal}'")
    print(f"==========================================")

    history = []
    for step in range(1, max_steps + 1):
        print(f"\n[Step {step}/{max_steps}] Perceiving screen state...")
        elements = device.dump_ui()
        print(f"[+] Detected {len(elements)} screen elements.")

        raw_plan = query_planner(goal, elements, history)
        clean_plan = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_plan.strip(), flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", clean_plan, re.DOTALL)
        if match:
            plan = json.loads(match.group(0))
        else:
            plan = json.loads(clean_plan)

        thought = plan.get("thought", "")
        action = plan.get("action", "")
        is_done = plan.get("done", False)

        print(f"[🤔 Planner Thought]: {thought}")
        print(f"[⚡ Decision]: Action='{action}'")

        if is_done or action == "done":
            print(f"\n✅ [Task Complete]: Goal '{goal}' achieved successfully!")
            break

        if action == "tap":
            x = plan.get("x")
            y = plan.get("y")
            if x is not None and y is not None:
                device.tap(x, y)
        elif action == "type":
            text = plan.get("text", "")
            device.type_text(text)
        elif action == "swipe":
            device.swipe(500, 1500, 500, 500)
        elif action == "key":
            code = plan.get("keycode", 4)
            device.key(code)
        elif action == "launch_app":
            pkg = plan.get("package", "")
            if pkg:
                device.launch_app(pkg)
        elif action == "intent":
            cmd = plan.get("intent_cmd", "")
            if cmd:
                device.shell(cmd)

        history.append({"step": step, "action": action, "thought": thought})
        time.sleep(1.2)

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].lower() in ("-h", "--help", "help"):
        print("Usage: python autoglm_agent.py \"<user goal>\"")
        print("\nOptions:")
        print("  -h, --help, help    Show this help message and exit")
        print("\nExamples:")
        print("  python autoglm_agent.py \"Tap on Settings\"")
        print("  python autoglm_agent.py \"Open Wi-Fi and connect\"")
        sys.exit(0)

    task_goal = " ".join(sys.argv[1:]).strip()
    run_autonomous_agent(task_goal)

