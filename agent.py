#!/usr/bin/env python3
"""
Autonomous Android Agent (Dual-Mode: Control + Search)
Designed for Samsung Galaxy M56 / Tab S9 FE+ via Shizuku (rish) & ADB.
Supports OpenRouter & Primary Flash Endpoints with sub-300ms latency.
"""

import os
import sys
import json
import re
import shutil
import urllib.parse
import subprocess
import requests

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ==========================================
# 1. Configuration & Key Management
# ==========================================
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

GROQ_KEYS = [os.environ.get(f"GROQ_API_KEY_{i}", "") for i in range(1, 6)]
GROQ_KEYS = [k for k in GROQ_KEYS if k] or ([os.environ.get("GROQ_API_KEY", "")] if os.environ.get("GROQ_API_KEY") else [])

PRIMARY_FLASH_KEYS = [os.environ.get(f"PRIMARY_FLASH_KEY_{i}", "") for i in range(1, 8)]
PRIMARY_FLASH_KEYS = [k for k in PRIMARY_FLASH_KEYS if k] or ([os.environ.get("PRIMARY_FLASH_API_KEY", "")] if os.environ.get("PRIMARY_FLASH_API_KEY") else [])

OPENROUTER_KEYS = [os.environ.get(f"OR_KEY_{i}", "") for i in range(1, 8)]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k] or ([os.environ.get("OPENROUTER_API_KEY", "")] if os.environ.get("OPENROUTER_API_KEY") else [])

SERPER_KEY = os.environ.get("SERPER_API_KEY", "")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
ADB_TARGET = os.environ.get("ADB_TARGET", "")

def _resolve_adb_binary():
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
    return env_bin or "adb"

ADB_BIN = _resolve_adb_binary()

SYSTEM_PROMPT = """You are the Autonomous Android System Controller & AI Agent running on a Samsung Galaxy device (SM-M566B).
You have full rootless shell access (UID 2000 / ADB / Shizuku).
You natively understand requests in English, Bengali (বাংলা), and Hindi (हिंदी). Translate non-English requests into exact Android actions.

Given a natural language user request, determine the action required:
1. "action": Executing Android intents, shell commands, app operations, hardware toggles, or automated UI clicks.
2. "search": Querying real-time information, web results, or facts.
3. "info": Answering direct questions or conversational prompts.

Output ONLY valid JSON in this exact structure without any markdown fencing:
{
  "type": "action" | "search" | "info",
  "command": "<valid adb/rish shell command(s) separated by && or empty>",
  "search_query": "<search query string if type is search, else empty>",
  "response": "<spoken or displayed confirmation for the user>"
}

Common Fast Intent Templates (Always use explicit -p package flag to prevent URLCheck/interceptors):
- YouTube Search (ReVanced): am start -p app.revanced.android.youtube -a android.intent.action.VIEW -d "https://www.youtube.com/results?search_query=<url_encoded_query>"
- YouTube Music (ReVanced): am start -p app.revanced.android.apps.youtube.music -a android.intent.action.VIEW -d "https://music.youtube.com/search?q=<url_encoded_query>"
- WhatsApp Business Message: am start -p com.whatsapp.w4b -a android.intent.action.VIEW -d "https://api.whatsapp.com/send?phone=<phone>&text=<url_encoded_msg>"
- Web Browsing (Chrome): am start -p com.android.chrome -a android.intent.action.VIEW -d "<url>"
- Launch App: monkey -p <package_name> -c android.intent.category.LAUNCHER 1
  * Termux: com.termux
  * MacroDroid: com.arlosoft.macrodroid
  * WhatsApp: com.whatsapp.w4b
  * ReVanced YouTube: app.revanced.android.youtube
  * Chrome: com.android.chrome
  * Settings: com.android.settings
  * Camera: am start -a android.media.action.STILL_IMAGE_CAMERA
- Hardware & System Toggles:
  * Flashlight Toggle: am broadcast -a com.termux.api.ACTION -n com.termux.api/.TermuxApiReceiver --es api_method torch --ez enabled true
  * Volume Up: input keyevent 24 / Volume Down: input keyevent 25
  * Expand Notifications: cmd statusbar expand-notifications
  * Collapse Notifications: cmd statusbar collapse
  * Home: input keyevent 3 / Back: input keyevent 4 / Recents: input keyevent 187
  * Screen Lock/Power: input keyevent 26
  * Take Screenshot: screencap -p /sdcard/Download/agent_screenshot.png
- Direct Phone Call: am start -a android.intent.action.CALL -d "tel:<phone>"
- Set Alarm: am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR <hour> --ei android.intent.extra.alarm.MINUTES <minute> --es android.intent.extra.alarm.MESSAGE "<message>" --ez android.intent.extra.alarm.SKIP_UI true
- Navigation: am start -a android.intent.action.VIEW -d "google.navigation:q=<destination>"
- Read Notifications: dumpsys notification --noredact
- Mode Presets:
  * Study: cmd media_session volume --stream 3 --set 0 && settings put system screen_brightness 76 && settings put global zen_mode 1
  * Outdoor: cmd media_session volume --stream 3 --set 15 && settings put system screen_brightness 255
  * Bedtime: cmd media_session volume --stream 3 --set 0 && settings put system screen_brightness 10 && settings put global zen_mode 1
  * Normal: cmd media_session volume --stream 3 --set 9 && settings put system screen_brightness 128 && settings put global zen_mode 0
"""

def clean_json_text(raw_text):
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return match.group(0)
    return clean

def query_llm(prompt_text):
    # 1. Try Primary Flash Endpoints (7 independent keys)
    if PRIMARY_FLASH_KEYS:
        primary_models = [m.strip() for m in os.environ.get("PRIMARY_FLASH_MODELS", "flash-lite-latest,flash-latest,flash-preview").split(",") if m.strip()]
        for key in PRIMARY_FLASH_KEYS:
            for model in primary_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    payload = {
                        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": [{"parts": [{"text": prompt_text}]}],
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
                            {"role": "user", "content": prompt_text}
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
                            {"role": "user", "content": prompt_text}
                        ],
                        "temperature": 0.1
                    }
                    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=8)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"]
                except Exception:
                    continue

    raise RuntimeError("All 19 LLM keys across Primary Flash, Groq, and OpenRouter failed or rate limited.")

def perform_web_search(query):
    q = str(query or "").strip()
    if not q:
        return "No search query provided."

    serper_key = os.environ.get("SERPER_API_KEY") or SERPER_KEY
    tavily_key = os.environ.get("TAVILY_API_KEY") or TAVILY_KEY

    # 1. Primary: Serper API
    if serper_key:
        try:
            headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
            payload = {"q": q}
            res = requests.post("https://google.serper.dev/search", headers=headers, json=payload, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if "answerBox" in data:
                    ab = data["answerBox"]
                    ans = ab.get("answer") or ab.get("snippet") or ab.get("title")
                    if ans:
                        return str(ans).strip()
                if "knowledgeGraph" in data:
                    kg = data["knowledgeGraph"]
                    desc = kg.get("description") or kg.get("title")
                    if desc:
                        return str(desc).strip()
                if "organic" in data and len(data["organic"]) > 0:
                    snippets = [org.get("snippet", "") for org in data["organic"][:3] if org.get("snippet")]
                    if snippets:
                        return " ".join(snippets)
        except Exception:
            pass

    # 2. Fallback: Tavily API
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {"api_key": tavily_key, "query": q, "search_depth": "basic", "include_answer": True}
            res = requests.post(url, json=payload, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data.get("answer"):
                    return str(data["answer"]).strip()
                results = data.get("results", [])
                snippets = [f"- {r.get('title')}: {r.get('content')}" for r in results[:3] if r.get("content")]
                if snippets:
                    return "\n".join(snippets)
        except Exception as e:
            return f"Search error: {e}"

    if not serper_key and not tavily_key:
        return "Web search requested, but neither SERPER_API_KEY nor TAVILY_API_KEY is configured."
    return "No search results found."

def execute_command(cmd_str):
    if not cmd_str:
        return

    is_android = os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", "")
    rish_path = "/system/bin/rish" if os.path.exists("/system/bin/rish") else "rish"
    has_rish = subprocess.run(f"command -v {rish_path}", shell=True, capture_output=True).returncode == 0

    if is_android and has_rish:
        print(f"[⚡ rish] Executing: {cmd_str}")
        full_cmd = f'{rish_path} -c {json.dumps(cmd_str)}'
        subprocess.run(full_cmd, shell=True)
    elif is_android:
        print(f"[⚡ local shell] Executing: {cmd_str}")
        subprocess.run(cmd_str, shell=True)
    else:
        print(f"[⚡ ADB -> {ADB_TARGET}] Executing: {cmd_str}")
        target_args = ["-s", ADB_TARGET] if ADB_TARGET else []
        res = subprocess.run([ADB_BIN] + target_args + ["shell", cmd_str], capture_output=True, encoding="utf-8", errors="replace")
        if (res.stdout or "").strip():
            print(f"[Output]: {(res.stdout or '').strip()}")
        if res.stderr.strip():
            print(f"[Error]: {res.stderr.strip()}")

def main():
    if len(sys.argv) < 2 or sys.argv[1].lower() in ("-h", "--help", "help"):
        print("Usage: python agent.py \"<natural language command or question>\"")
        print("\nOptions:")
        print("  -h, --help, help    Show this help message and exit")
        print("\nExamples:")
        print("  python agent.py \"turn on the flashlight\"")
        print("  python agent.py \"search for latest advances in nuclear fusion\"")
        sys.exit(0)


    user_prompt = " ".join(sys.argv[1:]).strip()
    print(f"\n[+] User: {user_prompt}")

    try:
        raw_output = query_llm(user_prompt)
        json_str = clean_json_text(raw_output)
        payload = json.loads(json_str)

        req_type = payload.get("type", "info")
        command = payload.get("command", "")
        search_q = payload.get("search_query", "")
        response = payload.get("response", "")

        if response:
            print(f"[🤖 Agent]: {response}")

        if req_type == "action" and command:
            execute_command(command)

        elif req_type == "search" and search_q:
            print(f"[🔍 Searching]: {search_q}")
            search_result = perform_web_search(search_q)
            print(f"[🌐 Results]:\n{search_result}")

    except Exception as e:
        print(f"[-] Execution Error: {e}")

if __name__ == "__main__":
    main()
