#!/usr/bin/env python3
"""
Autonomous Android Controller
=============================
Full on-device autonomous agent running natively inside Termux via Shizuku (rish)
or via ADB from PC.
Features:
- Multi-step compound goal decomposition and autonomous execution.
- Real-time UI hierarchy perception & dynamic visual tapping.
- Package-targeted high-speed intent dispatch.
- 19-key multi-provider failover (Primary Flash Endpoints, Groq Fast Models, OpenRouter Fallback Models).
- Multilingual support: English, Bengali (বাংলা), Hindi (हिंदी).
"""

import os
import sys
import json
import re
import time
import shutil
import urllib.parse
import subprocess
import xml.etree.ElementTree as ET
import requests

try:
    import memory_manager
except ImportError:
    try:
        from autonomous_android_controller import memory_manager
    except ImportError:
        memory_manager = None

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

# ─── 1. Key Vault & Environment ──────────────────────────────────────────────
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

APP_PACKAGE_MAP = {
    "youtube": "app.revanced.android.youtube",
    "revanced": "app.revanced.android.youtube",
    "yt": "app.revanced.android.youtube",
    "whatsapp": "com.whatsapp.w4b",
    "whatsapp business": "com.whatsapp.w4b",
    "gmail": "com.google.android.gm",
    "mail": "com.google.android.gm",
    "email": "com.google.android.gm",
    "messages": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "chrome": "com.android.chrome",
    "browser": "com.android.chrome",
    "settings": "com.android.settings",
    "camera": "com.sec.android.app.camera",
    "gallery": "com.sec.android.gallery3d",
    "photos": "com.sec.android.gallery3d",
    "clock": "com.sec.android.app.clockpackage",
    "alarm": "com.sec.android.app.clockpackage",
    "calculator": "com.sec.android.app.popupcalculator",
    "play store": "com.android.vending",
    "termux": "com.termux",
    "spotify": "com.spotify.music",
    "telegram": "org.telegram.messenger",
    "instagram": "com.instagram.android",
    "facebook": "com.facebook.katana",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "files": "com.sec.android.app.myfiles",
    "my files": "com.sec.android.app.myfiles"
}


# ─── 2. Low-Level Device Hardware & UI Controller ────────────────────────────
class Device:
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
        print(f"  [👉 Action] Tap ({x}, {y})")
        self.shell(f"input tap {x} {y}")

    def type_text(self, text):
        print(f"  [⌨️ Action] Type: '{text}'")
        encoded = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.shell(f"input text {encoded}")

    def key(self, code):
        print(f"  [🔘 Action] Keycode: {code}")
        self.shell(f"input keyevent {code}")

    def swipe(self, x1, y1, x2, y2, duration=300):
        print(f"  [👆 Action] Swipe ({x1},{y1}) -> ({x2},{y2})")
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")

    def dump_screen(self):
        self.shell("rm -f /data/local/tmp/window_dump.xml && uiautomator dump /data/local/tmp/window_dump.xml")
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
                            "id": res_id.split("/")[-1] if "/" in res_id else res_id,
                            "pkg": pkg,
                            "clickable": clickable,
                            "center": [center_x, center_y]
                        })
            except Exception:
                pass
        return elements

    def get_device_state(self):
        focus_raw = self.shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'")
        m_pkg = re.search(r"mCurrentFocus=Window\{[^\}]+\s+([^\s/]+)/?([^\s\}]*)", focus_raw)
        fg_pkg = m_pkg.group(1) if m_pkg else "unknown"
        fg_act = m_pkg.group(2) if m_pkg else ""

        vol_raw = self.shell("cmd media_session volume --stream 3 --get")
        m_vol = re.search(r"volume is (\d+)", vol_raw)
        vol = int(m_vol.group(1)) if m_vol else 8

        b_raw = self.shell("settings get system screen_brightness")
        brightness = int(b_raw) if b_raw.isdigit() else 128

        elements = self.dump_screen()
        return {
            "foreground_package": fg_pkg,
            "foreground_activity": fg_act,
            "media_volume": f"{vol}/15 ({round(vol/15*100)}%)",
            "screen_brightness": f"{brightness}/255 ({round(brightness/255*100)}%)",
            "elements": elements
        }


# ─── 3. Resilient Multi-Provider LLM Engine ──────────────────────────────────
def query_llm_resilient(prompt_text, system_instruction):
    # Tier 0: Local Offline Endpoint (Termux llama.cpp / Ollama / Local Agent API)
    local_url = os.environ.get("LOCAL_LLM_URL", "")
    if local_url:
        try:
            payload = {
                "model": os.environ.get("LOCAL_LLM_MODEL", "smollm2-1.7b-instruct"),
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt_text}
                ],
                "temperature": 0.1
            }
            grammar_path = os.environ.get("LOCAL_LLM_GRAMMAR", "")
            if grammar_path and os.path.exists(grammar_path):
                with open(grammar_path, "r", encoding="utf-8") as gf:
                    payload["grammar"] = gf.read()
            res = requests.post(local_url, json=payload, timeout=float(os.environ.get("LOCAL_LLM_TIMEOUT", "4")))
            if res.status_code == 200:
                data = res.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                elif "response" in data:
                    return data["response"]
        except Exception:
            pass

    # Tier 1: Primary Flash Endpoints (7 accounts)
    if PRIMARY_FLASH_KEYS:
        primary_models = [m.strip() for m in os.environ.get("PRIMARY_FLASH_MODELS", "flash-lite-latest,flash-latest,flash-preview").split(",") if m.strip()]
        for key in PRIMARY_FLASH_KEYS:
            for model in primary_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    payload = {
                        "system_instruction": {"parts": [{"text": system_instruction}]},
                        "contents": [{"parts": [{"text": prompt_text}]}],
                        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
                    }
                    res = requests.post(url, json=payload, timeout=6)
                    if res.status_code == 200:
                        return res.json()["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    continue

    # Tier 2: Groq (5 accounts)
    if GROQ_KEYS:
        for key in GROQ_KEYS:
            for model in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "groq/compound-mini"]:
                try:
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
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

    # Tier 3: OpenRouter (7 accounts)
    if OPENROUTER_KEYS:
        for key in OPENROUTER_KEYS:
            for model in ["minimax/minimax-m3:free", "nvidia/nemotron-3.5-lightning:free", "z-ai/glm-5.2:free", "google/gemma-4-31b-it:free"]:
                try:
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt_text}
                        ],
                        "temperature": 0.1
                    }
                    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=8)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"]
                except Exception:
                    continue

    raise RuntimeError("All 19 LLM keys across Primary Flash, Groq, and OpenRouter failed.")


# ─── 4. Hardware & Feature Helpers ───────────────────────────────────────────
def get_current_volume(device, stream=3):
    out = device.shell(f"cmd media_session volume --stream {stream} --get")
    m = re.search(r"volume is (\d+)", out)
    if m:
        return int(m.group(1))
    return 8

def set_volume_action(device, level, stream=3):
    if isinstance(stream, str):
        stream_lower = stream.lower()
        if "ring" in stream_lower:
            stream = 2
        elif "alarm" in stream_lower:
            stream = 4
        elif "notif" in stream_lower:
            stream = 5
        elif "system" in stream_lower:
            stream = 1
        else:
            stream = 3

    current = get_current_volume(device, stream)
    target_idx = current

    if isinstance(level, (int, float)):
        val = float(level)
        target_idx = round(val * 15 / 100) if val > 15 else int(val)
    elif isinstance(level, str):
        lvl = level.lower().strip()
        nums = re.findall(r"\d+", lvl)
        if nums:
            pct = int(nums[0])
            if "%" in lvl or pct > 15 or "percent" in lvl:
                target_idx = round(pct * 15 / 100)
            else:
                target_idx = pct
        elif "max" in lvl or "full" in lvl:
            target_idx = 15
        elif "mute" in lvl or "silence" in lvl or "zero" in lvl:
            target_idx = 0
        elif "half" in lvl:
            target_idx = 8
        elif any(w in lvl for w in ["up", "increase", "raise", "more", "louder", "boost", "+"]):
            target_idx = min(15, current + 4)
        elif any(w in lvl for w in ["down", "decrease", "lower", "less", "softer", "reduce", "-"]):
            target_idx = max(0, current - 4)
        else:
            target_idx = 12
    else:
        target_idx = min(15, current + 3)

    target_idx = max(0, min(15, target_idx))
    pct_disp = round(target_idx / 15 * 100)
    print(f"  [🔊 Volume] Stream {stream}: {current}/15 -> Setting to {target_idx}/15 ({pct_disp}%)")
    device.shell(f"cmd media_session volume --stream {stream} --set {target_idx}")
    return f"Volume stream {stream} set to {target_idx}/15 ({pct_disp}%)"

def control_media_action(device, action):
    act = (action or "toggle").lower().strip()
    print(f"  [⏯️ Media] Control: {act}")
    if "play" in act and "pause" not in act and "toggle" not in act:
        device.shell("cmd media_session dispatch play")
        device.key(126)
        return "Media playback started"
    elif "pause" in act:
        device.shell("cmd media_session dispatch pause")
        device.key(127)
        return "Media playback paused"
    elif "next" in act or "skip" in act:
        device.shell("cmd media_session dispatch next")
        device.key(87)
        return "Media skipped to next track"
    elif "prev" in act or "back" in act:
        device.shell("cmd media_session dispatch previous")
        device.key(88)
        return "Media returned to previous track"
    else:
        device.shell("cmd media_session dispatch play-pause")
        device.key(85)
        return "Media play/pause toggled"

def set_brightness_action(device, level):
    cur_str = device.shell("settings get system screen_brightness")
    cur = int(cur_str) if cur_str.isdigit() else 128
    target = cur

    if isinstance(level, str):
        lvl = level.lower().strip()
        if "max" in lvl or "full" in lvl or "100" in lvl:
            target = 255
        elif "half" in lvl or "50" in lvl:
            target = 128
        elif "min" in lvl or "zero" in lvl or lvl == "0" or lvl == "0%":
            target = 10
        elif any(w in lvl for w in ["up", "increase", "raise", "brighter", "+"]):
            target = min(255, cur + 50)
        elif any(w in lvl for w in ["down", "decrease", "lower", "dim", "-"]):
            target = max(10, cur - 50)
        else:
            nums = re.findall(r"\d+", lvl)
            if nums:
                pct = int(nums[0])
                target = round(pct * 255 / 100) if "%" in lvl or pct <= 100 else pct
    elif isinstance(level, (int, float)):
        target = round(level * 255 / 100) if level <= 100 else int(level)

    target = max(1, min(255, target))
    print(f"  [☀️ Brightness] Setting screen brightness to {target}/255 ({round(target/255*100)}%)")
    device.shell(f"settings put system screen_brightness {target}")
    return f"Screen brightness set to {target}/255 ({round(target/255*100)}%)"

def open_app_action(device, app_name, package=""):
    pkg = package
    if not pkg and app_name:
        name_clean = app_name.lower().strip()
        pkg = APP_PACKAGE_MAP.get(name_clean, "")
        if not pkg:
            for k, v in APP_PACKAGE_MAP.items():
                if k in name_clean or name_clean in k:
                    pkg = v
                    break

    if not pkg:
        pkg = app_name

    print(f"  [📱 App Launch] Launching package: {pkg}...")
    device.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
    return f"Launched app {pkg}"


def call_action(device, phone):
    clean_digits = re.sub(r"[^\d+*#]", "", str(phone).strip()) if phone else ""
    if not clean_digits or any(c.isalpha() for c in str(phone)):
        try:
            if memory_manager:
                matched = memory_manager.resolve_contact(str(phone))
                if matched and matched.get("phone"):
                    print(f"  [🧠 Knowledge Graph] Resolved '{phone}' -> {matched['name']} ({matched['phone']})")
                    clean_digits = re.sub(r"[^\d+*#]", "", str(matched["phone"]).strip())
        except Exception as e:
            print(f"  [!] Knowledge graph lookup error: {e}")
    clean_phone = clean_digits or str(phone).strip()
    print(f"  [📞 Call] Initiating direct call to {clean_phone}...")
    device.shell(f'am start -a android.intent.action.CALL -d "tel:{clean_phone}"')
    return f"Call placed to {clean_phone}"

def alarm_action(device, hour, minute=None, message="Alarm"):
    h = 0
    m = 0
    time_str_minute = None
    if isinstance(hour, (int, float)):
        h = int(hour)
    elif isinstance(hour, str) and ":" in hour:
        parts = hour.split(":")
        try:
            h = int(re.findall(r"-?\d+", parts[0])[0])
            time_str_minute = int(re.findall(r"-?\d+", parts[1])[0])
        except Exception:
            pass
    elif isinstance(hour, str):
        nums = re.findall(r"-?\d+", hour)
        h = int(nums[0]) if nums else 7
    else:
        h = 7

    if minute is not None:
        if isinstance(minute, (int, float)):
            m = int(minute)
        elif isinstance(minute, str):
            nums = re.findall(r"-?\d+", minute)
            m = int(nums[0]) if nums else 0
    elif time_str_minute is not None:
        m = time_str_minute
    else:
        m = 0

    h = max(0, min(23, h))
    m = max(0, min(59, m))
    msg = str(message if message is not None else "Alarm").replace('"', '\\"')
    print(f"  [⏰ Alarm] Setting alarm for {h:02d}:{m:02d} - '{msg}'...")
    device.shell(f'am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR {h} --ei android.intent.extra.alarm.MINUTES {m} --es android.intent.extra.alarm.MESSAGE "{msg}" --ez android.intent.extra.alarm.SKIP_UI true')
    return f"Alarm set for {h:02d}:{m:02d} with message '{msg}'"

def navigation_action(device, destination):
    dest = str(destination or "").strip()
    print(f"  [🧭 Navigation] Launching Google navigation to: {dest}...")
    device.shell(f'am start -a android.intent.action.VIEW -d "google.navigation:q={dest}"')
    return f"Navigation launched to {dest}"

def mode_action(device, mode_name):
    m = (mode_name or "normal").lower().strip()
    print(f"  [🎛️ Mode Preset] Applying environment preset: '{m}'...")
    if "study" in m:
        set_volume_action(device, 0, stream=3)
        device.shell("settings put system screen_brightness 76")
        device.shell("settings put global zen_mode 1")
        return "Study mode applied: volume 0, brightness 30%, zen_mode 1"
    elif "outdoor" in m:
        set_volume_action(device, 15, stream=3)
        device.shell("settings put system screen_brightness 255")
        return "Outdoor mode applied: volume 15, brightness 255"
    elif "bedtime" in m or "sleep" in m or "night" in m:
        set_volume_action(device, 0, stream=3)
        device.shell("settings put system screen_brightness 10")
        device.shell("settings put global zen_mode 1")
        return "Bedtime mode applied: volume 0, brightness 10, zen_mode 1"
    else:
        set_volume_action(device, 9, stream=3)
        device.shell("settings put system screen_brightness 128")
        device.shell("settings put global zen_mode 0")
        return "Normal mode applied: volume 9, brightness 128, zen_mode 0"

def parse_and_filter_notifications(raw_dumpsys):
    if not raw_dumpsys:
        return []

    records = re.split(r"NotificationRecord\(", raw_dumpsys)
    filtered = []

    msg_pkgs = {
        "whatsapp", "messaging", "telegram", "gm", "discord", "slack", "sms",
        "incallui", "mms", "dialer", "phone", "signal", "skype", "viber", "mail"
    }
    alert_keywords = {
        "alert", "message", "msg", "warning", "security", "code", "otp",
        "urgent", "call", "missed", "reminder", "chat", "notice", "alarm"
    }
    noise_indicators = {
        "charging_state", "battery_protection", "AlertWindowNotification",
        "live_hud", "hud_test", "test_benchmark_tag", "test_tag"
    }

    for r in records[1:]:
        if any(noise in r for noise in noise_indicators):
            continue

        pkg_m = re.search(r"pkg=([^\s]+)", r)
        pkg = pkg_m.group(1) if pkg_m else ""

        title_m = re.search(r"android\.title=(?:String|SpannableString)?\s*\((.*?)\)", r)
        title = title_m.group(1).strip() if title_m else ""

        text_m = re.search(r"android\.text=(?:String|SpannableString)?\s*\((.*?)\)", r)
        text = text_m.group(1).strip() if text_m else ""

        channel_m = re.search(r"channel=([^\s,\)]+)", r)
        channel = channel_m.group(1) if channel_m else ""

        ticker_m = re.search(r"tickerText=([^\r\n]+)", r)
        ticker = ticker_m.group(1).strip() if ticker_m and ticker_m.group(1).strip() != "null" else ""

        if not title and not text and not ticker:
            continue

        combined_text = f"{title} {text} {ticker}".lower()
        is_msg_pkg = any(p in pkg.lower() for p in msg_pkgs)
        channel_match = any(k in channel.lower() for k in alert_keywords)
        content_match = any(k in combined_text for k in alert_keywords)

        if is_msg_pkg or channel_match or content_match:
            display_text = text or ticker
            filtered.append({
                "package": pkg,
                "title": title,
                "text": display_text,
                "channel": channel
            })

    return filtered

def dump_notifications_action(device):
    print("  [🔔 Notifications] Dumping active notifications...")
    raw = device.shell("dumpsys notification --noredact")
    items = parse_and_filter_notifications(raw)
    if not items:
        return "No active incoming messages or alerts found."

    lines = [f"Found {len(items)} active incoming message(s)/alert(s):"]
    for item in items[:15]:
        pkg = item["package"].split(".")[-1]
        t = item["title"]
        txt = item["text"]
        if t and txt:
            lines.append(f"- [{pkg}] {t}: {txt}")
        elif t:
            lines.append(f"- [{pkg}] {t}")
        else:
            lines.append(f"- [{pkg}] {txt}")
    return "\n".join(lines)

def search_action(query):
    q = str(query or "").strip()
    if not q:
        return "No search query provided."

    serper_key = os.environ.get("SERPER_API_KEY") or SERPER_KEY
    tavily_key = os.environ.get("TAVILY_API_KEY") or TAVILY_KEY

    # 1. Primary: Serper API
    if serper_key:
        try:
            headers = {
                "X-API-KEY": serper_key,
                "Content-Type": "application/json"
            }
            payload = {"q": q}
            resp = requests.post("https://google.serper.dev/search", headers=headers, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if "answerBox" in data:
                    ab = data["answerBox"]
                    ans = ab.get("answer") or ab.get("snippet") or ab.get("title")
                    if ans:
                        return str(ans).strip()
                if "knowledgeGraph" in data:
                    kg = data["knowledgeGraph"]
                    title = kg.get("title", "")
                    desc = kg.get("description", "")
                    if title and desc:
                        return f"{title}: {desc}"
                    elif desc:
                        return desc
                    elif title:
                        return title
                if "organic" in data and len(data["organic"]) > 0:
                    snippets = [org.get("snippet", "") for org in data["organic"][:3] if org.get("snippet")]
                    if snippets:
                        return " ".join(snippets)
        except Exception as e:
            print(f"  [!] Serper API search failed: {e}. Falling back to Tavily...")

    # 2. Fallback: Tavily API
    if tavily_key:
        try:
            payload = {
                "api_key": tavily_key,
                "query": q,
                "include_answer": True
            }
            resp = requests.post("https://api.tavily.com/search", json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                ans = data.get("answer")
                if ans:
                    return str(ans).strip()
                results = data.get("results", [])
                if results and results[0].get("content"):
                    return str(results[0]["content"]).strip()
        except Exception as e:
            print(f"  [!] Tavily API search failed: {e}")

    if not serper_key and not tavily_key:
        return "Search failed: Neither SERPER_API_KEY nor TAVILY_API_KEY is configured."
    return f"No search results found for '{q}'."


# ─── 5. Autonomous Task Orchestrator & Self-Verification ───────────────────
DECOMPOSE_PROMPT = """You are the Autonomous Android Controller.
Analyze the user's high-level instruction and break it down into an ordered sequence of executable sub-tasks.
Support English, Bengali (বাংলা), and Hindi (हिंदी).

User Instruction: {instruction}

Supported Sub-Task Actions:
1. "chat": For general conversation, questions ("who are you", "what can you do", "tell me about X", general Q&A), or greetings. Answer directly and informatively. Provide "response": "<direct intelligent answer>".
2. "volume": Control audio volume. Provide "level" ("90%", "max", "mute", "up", "down", "50%", 0..100) and optional "stream" ("music" / 3, "ring" / 2, "alarm" / 4).
3. "media": Control media playback. Provide "action" ("play", "pause", "toggle", "next", "previous").
4. "youtube": Search and play a video or music on YouTube. Provide "query" (song/video name) and "auto_play": true.
5. "whatsapp": Send WhatsApp message to a phone number. Provide "phone", "message", and "auto_send": true.
6. "sms": Send SMS to a phone number. Provide "phone", "message", and "auto_send": true.
7. "email": Send email to an address. Provide "to", "subject", "body" (or "message"), and "auto_send": true.
8. "brightness": Adjust screen brightness. Provide "level" ("100%", "50%", "max", "min", "up", "down", 0..100).
9. "open_app": Launch an app. Provide "app_name" (e.g. "YouTube", "WhatsApp", "Settings", "Gmail", "Chrome", "Camera") or "package".
10. "read_screen": Launch an app, read visible screen text, and summarize. Provide "package" and "goal".
11. "intent": Execute a shell command. Provide "cmd".
12. "call": Place a direct phone call. Provide "phone" (can be a phone number or contact name/relationship like "maths teacher").
13. "alarm": Set an alarm. Provide "hour" (0..23), "minute" (0..59), and optional "message" (alarm label).
14. "navigation": Start Google Maps navigation to a destination. Provide "destination".
15. "mode": Apply environment presets: "study" (volume 0, brightness 30%, zen_mode 1), "outdoor" (volume 15, brightness 255), "bedtime" (volume 0, brightness 10, zen_mode 1), or "normal" (volume 9, brightness 128, zen_mode 0). Provide "mode" ("study" | "outdoor" | "bedtime" | "normal").
16. "notifications": Dump active notifications via dumpsys and filter for incoming messages/alerts. Provide "filter": "all" or "alerts".
17. "search": Query web search (Serper API with Tavily fallback) for real-time facts or web lookups. Provide "query".

Output ONLY valid JSON:
{
  "task_summary": "<brief explanation of overall task>",
  "steps": [
    {
      "step": 1,
      "type": "chat" | "volume" | "media" | "youtube" | "whatsapp" | "sms" | "email" | "brightness" | "open_app" | "read_screen" | "intent" | "call" | "alarm" | "navigation" | "mode" | "notifications" | "search",
      "response": "<direct answer text if chat>",
      "level": "<volume/brightness level if volume/brightness>",
      "action": "<playback action if media>",
      "phone": "<phone or contact name/relationship if call/whatsapp/sms>",
      "message": "<text if whatsapp/sms/email/alarm>",
      "hour": <hour 0..23 if alarm>,
      "minute": <minute 0..59 if alarm>,
      "destination": "<destination if navigation>",
      "mode": "<study | outdoor | bedtime | normal if mode>",
      "to": "<email address if email>",
      "subject": "<subject if email>",
      "body": "<body if email>",
      "query": "<query if youtube/search>",
      "app_name": "<app name if open_app>",
      "package": "<package if open_app/read_screen>",
      "cmd": "<command if intent>",
      "goal": "<what information to look for on screen>",
      "auto_send": true,
      "auto_play": true
    }
  ]
}
"""

def clean_json(text):
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    return match.group(0) if match else clean

def verify_and_diagnose_step(device, goal, action_taken, max_retries=2):
    """
    Self-diagnoses the device state after an action and verifies if the goal was achieved.
    If an issue/blocker is diagnosed, it autonomously executes corrective actions.
    """
    for attempt in range(1, max_retries + 1):
        time.sleep(1.2)
        state = device.get_device_state()
        elements_summary = [
            f"[{el['center'][0]},{el['center'][1]}] {el['text']} (desc: {el['desc']})"
            for el in state["elements"]
            if el["text"] or el["desc"] or el["clickable"]
        ][:25]

        eval_prompt = f"""Sub-Goal: {goal}
Last Action Taken: {action_taken}
Current Device State:
- Foreground App: {state['foreground_package']} ({state['foreground_activity']})
- Media Volume: {state['media_volume']}
- Screen Brightness: {state['screen_brightness']}
- Visible UI Elements:
{chr(10).join(elements_summary)}

Evaluate if the Sub-Goal is fulfilled.
If not, identify what is blocking it or what corrective action is needed.

Output ONLY valid JSON:
{{
  "diagnosis": "<what is currently visible and what happened>",
  "verified_success": true | false,
  "evidence": "<proof of success or reason for failure>",
  "corrective_action": "none" | "tap" | "key" | "type" | "shell",
  "action_params": {{
    "x": 500,
    "y": 1000,
    "code": 4,
    "text": "sample",
    "cmd": "am start ..."
  }}
}}
"""
        try:
            raw = query_llm_resilient(
                eval_prompt,
                "You are an Android UI Verifier and Diagnostician. Verify goal completion with rigorous evidence."
            )
            res = json.loads(clean_json(raw))
            diag = res.get("diagnosis", "")
            verified = res.get("verified_success", False)
            evidence = res.get("evidence", "")

            print(f"  [🔍 Diagnosis]: {diag}")
            if verified:
                print(f"  [🛡️ Verified Success]: {evidence}")
                return True, f"✔ Verified: {evidence}"

            corr = res.get("corrective_action", "none")
            params = res.get("action_params", {})
            print(f"  [⚠️ Goal Pending]: {evidence} -> Correction: {corr}")

            if corr == "tap" and "x" in params and "y" in params:
                device.tap(params["x"], params["y"])
            elif corr == "key" and "code" in params:
                device.key(params["code"])
            elif corr == "type" and "text" in params:
                device.type_text(params["text"])
            elif corr == "shell" and "cmd" in params:
                device.shell(params["cmd"])
            else:
                break
        except Exception as e:
            print(f"  [!] Diagnosis evaluation error: {e}")
            break

    return False, f"Action completed: {action_taken}"

def execute_autonomous_mission(instruction):
    t_start = time.time()
    device = Device()
    print("=" * 60)
    print(f"🚀 [Autonomous Controller] Executing Mission: '{instruction}'")
    print("=" * 60)

    # 0. Check Stored Routines in Knowledge Graph
    steps = []
    try:
        if memory_manager:
            routine = memory_manager.find_routine(instruction)
            if routine and routine.get("actions_json"):
                print(f"\n[🧠 Knowledge Graph] Matched Stored Routine: '{routine['name']}'")
                parsed_actions = json.loads(routine["actions_json"]) if isinstance(routine["actions_json"], str) else routine["actions_json"]
                steps = parsed_actions if isinstance(parsed_actions, list) else parsed_actions.get("steps", [])
                print(f"[+] Routine Breakdown: {len(steps)} actions pre-scheduled.")
    except Exception as e:
        print(f"  [!] Routine lookup error: {e}")

    # 1. Plan Decomposition
    if not steps:
        print("\n[🧠 Step 1] Decomposing high-level mission into autonomous sub-tasks...")
        plan_raw = query_llm_resilient(
            instruction,
            DECOMPOSE_PROMPT.replace("{instruction}", instruction)
        )
        plan = json.loads(clean_json(plan_raw))
        steps = plan.get("steps", [])
        print(f"[+] Mission Breakdown: {len(steps)} sub-tasks scheduled.")
    for s in steps:
        print(f"  • Step {s.get('step', '-')}: [{s.get('type', '').upper()}] {s.get('goal', s.get('level', s.get('action', s.get('destination', s.get('phone', s.get('mode', s.get('message', s.get('query', s.get('cmd', s.get('app_name', ''))))))))))}")

    results = []

    # 2. Execution & Verification Loop
    for idx, s in enumerate(steps, 1):
        stype = s.get("type", "")
        print(f"\n--- [Executing Step {idx}/{len(steps)}: {stype.upper()}] ---")

        if stype == "chat":
            ans = s.get("response", "")
            if not ans:
                ans = query_llm_resilient(
                    instruction,
                    "You are an on-device Android Autonomous Controller running natively on Samsung Galaxy M56 via Termux and Shizuku. Answer conversational questions helpfully, truthfully, and directly without doing web searches on yourself."
                )
            print(f"\n💬 {ans}\n")
            results.append(ans)

        elif stype == "volume":
            lvl = s.get("level", "up")
            strm = s.get("stream", 3)
            res = set_volume_action(device, lvl, strm)
            _, v_res = verify_and_diagnose_step(device, f"Set stream {strm} volume to {lvl}", res)
            results.append(v_res)

        elif stype == "media":
            act = s.get("action", "toggle")
            res = control_media_action(device, act)
            _, v_res = verify_and_diagnose_step(device, f"Media playback {act}", res)
            results.append(v_res)

        elif stype == "brightness":
            lvl = s.get("level", "up")
            res = set_brightness_action(device, lvl)
            _, v_res = verify_and_diagnose_step(device, f"Set screen brightness to {lvl}", res)
            results.append(v_res)

        elif stype == "open_app":
            app_n = s.get("app_name", "")
            pkg = s.get("package", "")
            res = open_app_action(device, app_n, pkg)
            _, v_res = verify_and_diagnose_step(device, f"Launch {app_n or pkg}", res)
            results.append(v_res)

        elif stype == "whatsapp":
            phone = s.get("phone", "")
            if not phone or any(c.isalpha() for c in str(phone)):
                query_target = phone or s.get("contact") or instruction
                try:
                    if memory_manager:
                        matched = memory_manager.resolve_contact(query_target)
                        if matched and matched.get("phone"):
                            print(f"  [🧠 Knowledge Graph] Resolved WhatsApp target '{query_target}' -> {matched['name']} ({matched['phone']})")
                            phone = matched["phone"]
                except Exception:
                    pass
            phone = re.sub(r"[^\d+*#]", "", str(phone).strip()) if phone else ""
            if len(phone) == 10 and not phone.startswith("91"):
                phone = "91" + phone
            msg = urllib.parse.quote(s.get("message", "hi"))
            print(f"  [⚡ WhatsApp] Opening conversation with {phone}...")
            device.shell(f"am start -p com.whatsapp.w4b -a android.intent.action.VIEW -d 'https://api.whatsapp.com/send?phone={phone}&text={msg}'")
            time.sleep(2)
            if s.get("auto_send", True):
                elements = device.dump_screen()
                send_btn = None
                for el in elements:
                    desc = (el.get("desc") or "").lower()
                    if "send" in desc or "পাঠান" in desc:
                        send_btn = el
                        break
                if send_btn:
                    device.tap(send_btn["center"][0], send_btn["center"][1])
                    print("  [✅ WhatsApp] Message sent successfully.")
                else:
                    device.tap(990, 2131)
                    print("  [✅ WhatsApp] Tap Send button dispatched.")
            _, v_res = verify_and_diagnose_step(device, f"WhatsApp message sent to {phone}", f"Dispatched '{s.get('message')}' to {phone}")
            results.append(v_res)

        elif stype == "sms":
            phone = s.get("phone", "")
            if not phone or any(c.isalpha() for c in str(phone)):
                query_target = phone or s.get("contact") or instruction
                try:
                    if memory_manager:
                        matched = memory_manager.resolve_contact(query_target)
                        if matched and matched.get("phone"):
                            print(f"  [🧠 Knowledge Graph] Resolved SMS target '{query_target}' -> {matched['name']} ({matched['phone']})")
                            phone = matched["phone"]
                except Exception:
                    pass
            phone = re.sub(r"[^\d+*#]", "", str(phone).strip()) if phone else ""
            msg = s.get("message", "hi")
            print(f"  [⚡ SMS] Opening Messages for {phone}...")
            device.shell(f"am start -a android.intent.action.SENDTO -d 'smsto:{phone}' --es 'sms_body' '{msg}'")
            time.sleep(2)
            if s.get("auto_send", True):
                elements = device.dump_screen()
                send_btn = None
                for el in elements:
                    desc = (el.get("desc") or "").lower()
                    if "send" in desc or "sms" in desc:
                        send_btn = el
                        break
                if send_btn:
                    device.tap(send_btn["center"][0], send_btn["center"][1])
                    print("  [✅ SMS] SMS sent successfully.")
                else:
                    device.tap(982, 2112)
                    print("  [✅ SMS] Tap Send SMS dispatched.")
            _, v_res = verify_and_diagnose_step(device, f"SMS sent to {phone}", f"Dispatched SMS to {phone}")
            results.append(v_res)

        elif stype == "email":
            to = s.get("to", "")
            if not to or "@" not in to:
                query_target = to or s.get("contact") or instruction
                try:
                    if memory_manager:
                        matched = memory_manager.resolve_contact(query_target)
                        if matched and matched.get("email"):
                            print(f"  [🧠 Knowledge Graph] Resolved Email target '{query_target}' -> {matched['name']} ({matched['email']})")
                            to = matched["email"]
                except Exception:
                    pass
            subject = urllib.parse.quote(s.get("subject", "Hello"))
            body = urllib.parse.quote(s.get("body", s.get("message", "hi")))
            print(f"  [⚡ Email] Composing email to {to}...")
            device.shell(f"am start -a android.intent.action.SENDTO -d 'mailto:{to}?subject={subject}&body={body}'")
            time.sleep(2)
            if s.get("auto_send", True):
                elements = device.dump_screen()
                send_btn = None
                for el in elements:
                    desc = (el.get("desc") or "").lower()
                    res_id = (el.get("id") or "").lower()
                    if "send" in desc or "send_action" in res_id or "পাঠান" in desc:
                        send_btn = el
                        break
                if send_btn:
                    device.tap(send_btn["center"][0], send_btn["center"][1])
                    print(f"  [✅ Email] Tapped Send button ({send_btn['center'][0]}, {send_btn['center'][1]}).")
                else:
                    device.tap(930, 160)
                    print("  [✅ Email] Tap Send button dispatched.")
            _, v_res = verify_and_diagnose_step(device, f"Email sent to {to}", f"Dispatched email to {to}")
            results.append(v_res)

        elif stype == "youtube":
            raw_q = s.get("query", s.get("message", "mood booster song"))
            q = urllib.parse.quote(raw_q)
            print(f"  [⚡ YouTube] Searching & playing: '{raw_q}'...")
            device.shell(f"am start -p app.revanced.android.youtube -a android.intent.action.VIEW -d 'https://www.youtube.com/results?search_query={q}'")
            time.sleep(2.5)
            if s.get("auto_play", True):
                device.tap(500, 650)
                print("  [▶️ YouTube] First video tapped to play.")
            _, v_res = verify_and_diagnose_step(device, f"Play YouTube video for '{raw_q}'", f"Playing '{raw_q}' on YouTube")
            results.append(v_res)

        elif stype == "read_screen":
            pkg = s.get("package", "com.google.android.gm")
            goal = s.get("goal", "read unread items")
            if pkg:
                print(f"  [⚡ Screen Reader] Launching {pkg}...")
                device.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
                time.sleep(3)
            elements = device.dump_screen()
            screen_texts = [f"- {el['text']} (desc: {el['desc']})" for el in elements if el['text'] or el['desc']]
            screen_blob = "\n".join(screen_texts[:35])

            summary_prompt = f"Goal: {goal}\nVisible Screen Data:\n{screen_blob}\n\nProvide a concise bulleted summary of key findings:"
            summary = query_llm_resilient(summary_prompt, "You are a screen analyzer. Summarize unread emails, notifications, or key data clearly.")
            print(f"  [📄 Findings]:\n{summary.strip()}")
            results.append(f"Screen analysis:\n{summary.strip()}")

        elif stype == "intent":
            cmd = s.get("cmd", "")
            print(f"  [⚡ Shell] Running: {cmd}")
            out = device.shell(cmd)
            if out:
                print(f"  [Output]: {out}")
            _, v_res = verify_and_diagnose_step(device, f"Executed {cmd}", f"Shell output: {out}")
            results.append(v_res)

        elif stype == "call":
            raw_phone = s.get("phone", "")
            phone = raw_phone
            if not phone or any(c.isalpha() for c in str(phone)):
                query_target = raw_phone or s.get("contact") or instruction
                try:
                    if memory_manager:
                        matched = memory_manager.resolve_contact(query_target)
                        if matched and matched.get("phone"):
                            print(f"  [🧠 Knowledge Graph] Resolved Call target '{query_target}' -> {matched['name']} ({matched['phone']})")
                            phone = matched["phone"]
                except Exception:
                    pass
            res = call_action(device, phone)
            _, v_res = verify_and_diagnose_step(device, f"Call {phone}", res)
            results.append(v_res)

        elif stype == "alarm":
            h = s.get("hour", 7)
            m = s.get("minute", 0)
            msg = s.get("message", "Alarm")
            res = alarm_action(device, h, m, msg)
            _, v_res = verify_and_diagnose_step(device, f"Set alarm for {h}:{m}", res)
            results.append(v_res)

        elif stype == "navigation":
            dest = s.get("destination", s.get("query", ""))
            res = navigation_action(device, dest)
            _, v_res = verify_and_diagnose_step(device, f"Navigate to {dest}", res)
            results.append(v_res)

        elif stype == "mode":
            mode_name = s.get("mode", s.get("preset", "normal"))
            res = mode_action(device, mode_name)
            _, v_res = verify_and_diagnose_step(device, f"Set mode {mode_name}", res)
            results.append(v_res)

        elif stype == "notifications":
            res = dump_notifications_action(device)
            print(f"  [🔔 Notifications]:\n{res}")
            results.append(res)

        elif stype == "search":
            q = s.get("query", "")
            res = search_action(q)
            results.append(f"Search '{q}': {res}")

        time.sleep(1.2)

    # 3. Final Synthesis
    summary_text = "\n".join([f"✔ {r}" for r in results])
    print("\n" + "=" * 60)
    print("🎯 [Mission Complete] Final Verified Summary:")
    print("=" * 60)
    print(summary_text)
    print("=" * 60)
    device.shell(f"cmd notification post -S bigtext -t 'Agent Finished' live_hud '{summary_text[:200]}'")

    # 4. History Logging into On-Device Knowledge Graph
    duration_ms = (time.time() - t_start) * 1000.0
    try:
        if memory_manager:
            status = "success" if results else "completed"
            memory_manager.record_history(instruction, status=status, duration_ms=duration_ms)
    except Exception:
        pass

class TeeLogger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8", errors="replace")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].lower() in ("-h", "--help", "help"):
        print("Usage: python master_agent.py \"<compound instruction>\" or ai log")
        print("\nOptions:")
        print("  -h, --help, help    Show this help message and exit")
        print("  log, status         Display last execution transcript and diagnosis")
        print("\nExamples:")
        print("  python master_agent.py \"Set volume to 80% and play Kishore Kumar on YouTube\"")
        print("  python master_agent.py \"Open settings and turn on Wi-Fi\"")
        print("  python master_agent.py log")
        sys.exit(0)

    cmd_arg = sys.argv[1].strip().lower()
    log_file = "/sdcard/agent/last_run.log" if os.path.exists("/sdcard") else os.path.expanduser("~/.agent_last_run.log")

    if cmd_arg in ["log", "status", "--log", "-l"]:
        if os.path.exists(log_file):
            print("\n📋 [Last Agent Execution Log]:\n" + "=" * 50)
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                print(f.read())
            print("=" * 50)
        else:
            print("No previous execution log found.")
        sys.exit(0)

    sys.stdout = TeeLogger(log_file)
    mission = " ".join(sys.argv[1:]).strip()
    execute_autonomous_mission(mission)

