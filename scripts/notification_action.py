#!/usr/bin/env python3
"""
Autonomous Android Controller — Notification Action Dispatcher
Handles action clicks directly from the Android Notification Shade:
  - scan: Captures and summarizes the current foreground screen/article
  - undo: Rolls back the last reversible action from action_journal
  - hud: Launches the floating web HUD
"""

import os
import sys
import json
import re
import subprocess
import xml.etree.ElementTree as ET

# Resolve paths
AGENT_DIR = "/sdcard/agent" if os.path.isdir("/sdcard/agent") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AGENT_DIR)

try:
    import memory_manager
    from memory_manager import get_memory_manager
except ImportError:
    memory_manager = None
    get_memory_manager = None


def run_shell(cmd):
    """Executes shell command locally or via ADB."""
    if os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", ""):
        res = subprocess.run(cmd, shell=True, capture_output=True, encoding="utf-8", errors="replace")
        return (res.stdout or "").strip()
    else:
        adb_target = os.environ.get("ADB_TARGET", "")
        adb_bin = "adb"
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            sdk_adb = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
            if os.path.exists(sdk_adb):
                adb_bin = sdk_adb
        args = [adb_bin]
        if adb_target:
            args.extend(["-s", adb_target])
        args.extend(["shell", cmd])
        res = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace")
        return (res.stdout or "").strip()


def post_bigtext_notification(title, summary, tag="Agent"):
    """Post an untruncated BigText notification visible in the notification panel."""
    clean_summary = summary.replace("'", "").replace('"', "")
    cmd = f"cmd notification post -S bigtext -t '{title}' '{tag}' '{clean_summary}'"
    run_shell(cmd)


def handle_undo():
    """Undo the last executed reversible action from the journal."""
    if not memory_manager or not get_memory_manager:
        post_bigtext_notification("Undo Error", "Memory manager unavailable.")
        return {"success": False, "error": "No memory manager"}

    mm = get_memory_manager()
    action = mm.get_last_reversible_action()
    if not action:
        post_bigtext_notification("Undo", "No recent reversible action found to undo.")
        return {"success": True, "message": "Nothing to undo"}

    inv_action = action.get("inverse_action")
    inv_params = action.get("inverse_params")
    journal_id = action.get("id")

    if isinstance(inv_params, str) and inv_params.startswith("{"):
        try:
            inv_params = json.loads(inv_params)
        except Exception:
            pass

    # Execute rollback
    msg = f"Reverted {action['forward_action']}."
    if inv_action == "volume":
        lvl = inv_params.get("level", 8) if isinstance(inv_params, dict) else inv_params
        run_shell(f"cmd media_session volume --stream 3 --set {lvl}")
        msg = f"Reverted volume back to {lvl}/15."
    elif inv_action == "brightness":
        lvl = inv_params.get("level", 128) if isinstance(inv_params, dict) else inv_params
        run_shell(f"settings put system screen_brightness {lvl}")
        msg = f"Reverted screen brightness to {lvl}."
    elif inv_action in ("key", "back"):
        run_shell("input keyevent 4")
        msg = "Dispatched BACK to dismiss opened application."
    elif inv_action == "collapse":
        run_shell("cmd statusbar collapse")
        msg = "Collapsed statusbar panels."
    else:
        run_shell(f"input keyevent 4")

    mm.mark_action_rolled_back(journal_id)
    post_bigtext_notification("Action Undone ↩", msg)
    return {"success": True, "undone": action, "message": msg}


def handle_scan():
    """Ambient Screen Perception: Scans foreground screen/article and summarizes."""
    # 1. Identify foreground app
    focus_raw = run_shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'")
    m_pkg = re.search(r"Window\{[^}]+\s+([^/\s]+)/?([^}\s]*)", focus_raw)
    pkg = m_pkg.group(1) if m_pkg else "Unknown"

    # 2. Dump screen hierarchy
    run_shell("rm -f /data/local/tmp/window_dump.xml && uiautomator dump /data/local/tmp/window_dump.xml")
    xml_str = run_shell("cat /data/local/tmp/window_dump.xml 2>/dev/null")

    texts = []
    if "<hierarchy" in xml_str:
        clean_xml = xml_str[xml_str.find("<hierarchy"):]
        try:
            root = ET.fromstring(clean_xml)
            for node in root.iter("node"):
                t = node.attrib.get("text", "").strip()
                if t and len(t) > 2 and t not in texts:
                    texts.append(t)
        except Exception:
            pass

    if not texts:
        msg = f"Screen scanned on {pkg}. No textual elements detected."
        post_bigtext_notification("Screen Scan 🔍", msg)
        return {"success": True, "foreground_app": pkg, "summary": msg}

    article_snippet = " ".join(texts[:40])

    # 3. Fast extractive / LLM summary
    summary_bullets = []
    # Title / Top heading
    summary_bullets.append(f"• Target Context: {pkg}")
    # Key content snippets
    key_phrases = [t for t in texts if len(t.split()) >= 3][:3]
    for kp in key_phrases:
        summary_bullets.append(f"• {kp}")

    full_summary = "\n".join(summary_bullets)
    post_bigtext_notification(f"Ambient Screen: {pkg}", full_summary)
    return {
        "success": True,
        "foreground_app": pkg,
        "extracted_nodes": len(texts),
        "summary": full_summary
    }


def handle_hud():
    """Launches local web HUD in user's browser."""
    run_shell("am start -a android.intent.action.VIEW -d 'http://127.0.0.1:5005/'")
    return {"success": True, "launched": "http://127.0.0.1:5005/"}


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if action == "undo":
        res = handle_undo()
    elif action == "hud":
        res = handle_hud()
    else:
        res = handle_scan()
    print(json.dumps(res, indent=2))
