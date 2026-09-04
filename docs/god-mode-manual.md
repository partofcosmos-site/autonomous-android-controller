# God-Mode Android Autonomous Controller — Operator Manual

Transform your **Samsung Galaxy M56 (SM-M566B)** into a fully autonomous, self-healing, AI-controlled phone with Shizuku UID 2000 shell privileges and complete OpenDroid parity.

---

## 1. Quick Start — 4 Ways to Control Your Phone

### Option A: Headless Shizuku God-Mode Background Daemon (No Active Terminal Required)
The God-Mode background daemon runs detached from any interactive terminal session, executing instructions via Shizuku (UID 2000) or ADB shell:
```bash
# Start background daemon on port 5005
bash /sdcard/agent/scripts/start_god_mode.sh
```
Send commands via simple HTTP REST API or file IPC:
```bash
# Gesture dispatch via curl
curl -X POST http://127.0.0.1:5005/tap -H "Content-Type: application/json" -d '{"x": 540, "y": 1200}'
curl -X POST http://127.0.0.1:5005/notifications/expand

# Autonomous instruction dispatch
curl -X POST http://127.0.0.1:5005/instruction -H "Content-Type: application/json" -d '{"instruction": "study mode"}'
```

### Option B: 1-Tap Termux CLI (Fastest On-Device CLI)
Open Termux and run:
```bash
ai "set volume to 40% and play lo-fi on revanced"
```
Or call any contact:
```bash
ai "call Math Teacher"
```

### Option C: Floating Button & Overlay Management (Remove vs God-Level Upgrade)
By default, the stock OpenDroid floating bubble is sluggish, intrusive, and lacks hardware power. You can completely remove it or upgrade it to God-Level:

```bash
# To completely remove and disable the floating button (Zero screen clutter):
sh /sdcard/agent/scripts/floating_controller.sh remove

# To check current floating button visibility:
sh /sdcard/agent/scripts/floating_controller.sh status

# To upgrade the floating button into God-Level (backed by bridge on port 4000):
sh /sdcard/agent/scripts/floating_controller.sh god-level
```

When upgraded to God-Level:
1. The floating button connects directly to `opendroid_bridge.py` on `http://127.0.0.1:4000/v1`.
2. Every voice or text input routes through our 19 rotating cloud keys + local offline model (`SmolLM2-1.7B-Instruct`).
3. Execution runs via Shizuku UID 2000 hardware gestures, direct intents, and Personal Knowledge Graph (`memory.db`).

### Option D: Wireless Remote Control from PC (ADB Host)
From your PC terminal inside `autonomous-android-controller`:
```powershell
python master_agent.py "study mode"
```

---

## 2. High-Impact Everyday Use Cases (Zero UI Friction)

| Intent Recipe | Natural Voice/Text Command | Execution Latency | Underlying Zero-Tap Intent |
| :--- | :--- | :--- | :--- |
| **Instant Messaging** | `"Send WhatsApp message to +15550199 saying I am on my way"` | ~150ms | `am start -a android.intent.action.VIEW -d "https://api.whatsapp.com/send?phone=...&text=..."` |
| **Instant Phone Call** | `"Call Math Teacher"` | ~100ms | `am start -a android.intent.action.CALL -d "tel:..."` |
| **Turn-by-Turn Navigation** | `"Navigate to Downtown in Maps"` | ~120ms | `am start -a android.intent.action.VIEW -d "google.navigation:q=Downtown"` |
| **Hands-Free Music** | `"Play Hans Zimmer in ReVanced"` | ~200ms | `am start -p app.revanced.android.youtube -a android.intent.action.VIEW -d "https://www.youtube.com/results?search_query=..."` |
| **Silent Study Preset** | `"Study mode"` | ~80ms | Volume 0%, Brightness 20%, Zen Mode (DND) ON |
| **Outdoor Max Preset** | `"Outdoor mode"` | ~80ms | Brightness 255 (100%), Volume 15 (100%), Launch Maps |
| **Bedtime Preset** | `"Bedtime mode"` | ~90ms | Brightness 10, Zen Mode ON, Volume 0% |
| **Instant Alarm** | `"Set alarm for 6:30 AM"` | ~50ms | `am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR 6 --ei android.intent.extra.alarm.MINUTES 30 --ez android.intent.extra.alarm.SKIP_UI true` |
| **Notification Reader** | `"Summarize my unread notifications"` | ~400ms | `dumpsys notification --noredact` + LLM extraction |

---

## 3. Shizuku God-Mode Native Gesture Parity

The God-Mode daemon (`god_daemon.py`) grants full parity with Android Accessibility Services while bypassing accessibility lag, battery overhead, and OneUI service kill policies by executing directly in UID 2000 shell context:

| Capability | God-Mode Native API | Shizuku / Shell Command | Parity Feature |
| :--- | :--- | :--- | :--- |
| **Tap** | `tap(x, y)` | `input tap <x> <y>` | Precise pixel-accurate touch dispatch |
| **Swipe** | `swipe(x1, y1, x2, y2, ms)` | `input swipe <x1> <y1> <x2> <y2> <ms>` | Smooth fluid gesture & drag simulation |
| **Text Typing** | `type_text(text)` | `am broadcast clipper` + `input text` | Special characters, quotes, and emoji handling |
| **Hardware Key** | `key(code)` | `input keyevent <code>` | Back (4), Home (3), Recents (187), Power (26) |
| **Expand Notifications** | `expand_notifications()` | `cmd statusbar expand-notifications` | Instant full notification shade pull-down |
| **Collapse Panels** | `collapse_panels()` | `cmd statusbar collapse` | Dismisses all active statusbar panels |
| **Quick Settings** | `open_quick_settings()` | `cmd statusbar expand-settings` | Instant Quick Settings tiles expansion |
| **Screen Capture** | `take_screenshot(path)` | `screencap -p <path>` | Hardware framebuffer capture in ~100ms |
| **Focused Activity** | `get_foreground_app()` | `dumpsys window` / `dumpsys activity` | Real-time foreground app package & activity |
| **Media Volume** | `get_volume()` | `cmd media_session volume --stream 3` | Quantized media volume inspection and control |

---

## 4. Storage Architecture & Termux Zero-Loss Recovery

### Android Storage Topology

Android enforces strict sandbox boundaries between application internal memory and shared storage:

```
/ (Root Filesystem)
├── data/data/com.termux/             <-- VOLATILE APPLICATION SANDBOX
│   ├── files/home/                   (Wiped during "Clear App Data" or OS cleaning)
│   └── files/usr/                    (Binaries, packages, python env)
│
└── storage/emulated/0/ (/sdcard/)    <-- NON-VOLATILE EXTERNAL SHARED STORAGE
    └── agent/                        (100% IMMUNE TO APP DATA WIPES)
        ├── models/                   --> 1.35GB SmolLM2-1.7B GGUF Model (Preserved)
        ├── memory.db                 --> SQLite Agent Long-Term Memory (Preserved)
        ├── .env                      --> Multi-Provider API Keys (Preserved)
        ├── master_agent.py           --> Core Autonomous Controller
        ├── god_daemon.py             --> Shizuku Background Daemon
        ├── opendroid_bridge.py       --> OpenAI-Compatible Bridge
        ├── daemon_queue/             --> Asynchronous IPC Task Queue
        ├── screenshots/              --> Framebuffer Captures
        └── scripts/
            ├── start_god_mode.sh     --> Daemon Launcher
            ├── restore_termux.sh     --> 30-Second Instant Recovery Script
            └── launch_offline_ai.sh  --> Offline llama-server Daemon
```

### Data Wipe Resilience Facts

1. **Why Termux Data Clears**:
   - User taps "Clear Data" in Android Settings -> Apps -> Termux.
   - Samsung OneUI Device Care / Deep Cleaner purges private application cache and databases.
   - Termux app package uninstalled and reinstalled.
   When this occurs, `/data/data/com.termux/` is reset to an empty state.

2. **Why Zero Agent Data is Lost**:
   - `/sdcard/agent` resides on Android's shared media partition (`/storage/emulated/0/`).
   - Android's package manager **never deletes** shared storage when clearing app data.
   - The 1.35GB local AI model, SQLite memory database, credentials, and custom scripts remain completely intact.

3. **1-Command Zero-Loss Recovery Protocol (< 30 Seconds)**:
   In a freshly cleared Termux terminal, run:
   ```bash
   pkg install -y curl && bash /sdcard/agent/scripts/restore_termux.sh
   ```
   What this executes automatically:
   - Re-installs Python, git, and curl in Termux (~10s).
   - Re-links `ln -s /sdcard/agent ~/agent`.
   - Links `$PREFIX/bin/ai` and `$PREFIX/bin/god-mode` global shortcuts.
   - Restores Termux:Widget shortcuts in `~/.shortcuts`.
   - Installs pip requirements from `/sdcard/agent/requirements.txt`.
   - Verifies the 1.35GB local model without re-downloading a single byte!

---

## 5. Offline AI Engine & Cloud Cascade

- **Tier 0 (Local Offline Engine)**: `SmolLM2-1.7B-Instruct` (Q4_K_M GGUF) via `llama-server` on `http://127.0.0.1:8080` with GBNF grammar constraints (`grammars/action.gbnf`).
- **Tier 1 (Google AI Studio)**: 7 rotating keys for ultra-fast frontier reasoning.
- **Tier 2 (Groq)**: 5 rotating keys for high-speed inference.
- **Tier 3 (OpenRouter)**: 7 rotating keys with automatic fallback.
