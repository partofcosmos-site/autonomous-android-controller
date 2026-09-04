# Engineering Post-Mortem & Roadblocks Overcome

---

## Executive Summary

Building an autonomous on-device mobile controller that reliably operates across arbitrary third-party Android applications requires navigating countless undocumented platform quirks, OEM modifications, and operating system security restrictions.

Naive approaches that work in desktop automation (such as standard synthetic clicks, raw bash aliases, or open-ended web searches) break down immediately on mobile. This document chronicles the critical engineering roadblocks encountered during the research and development of the **Autonomous Android Controller**, the exact root causes uncovered, and the production-grade architectural solutions designed to overcome them.

---

## Roadblock 1: Accessibility Service Tree Drops on Flutter/Canvas and Android 13+ Restricted Settings

### Symptom
Early automation prototypes relying on Android's `AccessibilityService` failed consistently across modern applications:
1. On applications built with Flutter or custom graphics engines, the controller reported finding zero clickable elements or treated the entire screen as a single blank canvas.
2. Sideloading the controller APK on Android 13+ devices presented users with an aggressive system dialog: *"Restricted setting: For your security, this setting is currently unavailable"*, requiring cumbersome multi-step security bypasses in system settings.
3. Continuous background accessibility monitoring caused severe battery drain (15–25% per hour) and system UI frame drops.

### Root Cause
- **Declarative & Canvas Rendering:** Flutter (using Skia / Impeller) and game engines render directly to raw GPU surfaces. Unless application authors explicitly annotate every widget with accessibility semantics, Android's `AccessibilityNodeInfo` tree builder remains completely blind to interactive elements.
- **Android 13+ Sideload Policy:** Android 13 introduced runtime restrictions for accessibility services bundled in applications installed from outside verified app stores to mitigate credential harvesting malware.
- **System Event Throttling:** The system `AccessibilityManagerService` throttles high-frequency event broadcasts under system load, dropping `TYPE_WINDOW_CONTENT_CHANGED` events.

### Engineering Solution: Rootless Privilege Escalation via Shizuku (`UID 2000`)
We completely bypassed the Accessibility framework in favor of **Shizuku's native `UID 2000` (`shell`) execution bridge**:
1. Invoking `uiautomator dump /data/local/tmp/window_dump.xml` via `rish` captures the full window hierarchy directly from the `WindowManagerService` at the system level, bypassing application-level accessibility gating.
2. Taps are executed using kernel-level synthetic input (`input tap X Y`), simulating true hardware digitizer touch events that work seamlessly regardless of whether the target application is built with native Views, Jetpack Compose, Flutter, WebViews, or game engines.
3. Eliminates sideloaded accessibility permission blocks entirely while preserving device integrity and SafetyNet / Play Integrity attestation.

---

## Roadblock 2: Android Phantom Process Killer Terminating Background Termux Processes

### Symptom
When executing compound missions involving multiple sub-tasks or running long background automation sessions inside Termux, Python scripts and helper processes were terminated abruptly without an exception traceback:
```
[Process completed (signal 9) - press Enter]
```
The terminal session died mid-mission, and all agent state was lost.

### Root Cause
Beginning with Android 12, Google integrated the **Phantom Process Killer** into the Linux kernel and `ActivityManager`. The OS monitors any child processes spawned by an unprivileged application outside of its main application cgroup:
- If the total system-wide count of phantom processes exceeds **32**, the OS aggressively sends `SIGKILL` (`kill -9`) to the processes consuming the most CPU or memory.
- When Termux executed Python, which in turn spawned `uiautomator`, `grep`, `cat`, or sub-shells, the phantom process limit was breached almost immediately during iterative ReAct loops.

### Engineering Solution: Permanent Privileged System Override
Because Shizuku provides `UID 2000` shell privileges, the controller executes a permanent system configuration patch directly modifying `device_config` and system settings:
```bash
# Expand the phantom process ceiling to the maximum 32-bit signed integer
rish -c "device_config put activity_manager max_phantom_processes 2147483647"

# Permanently disable the background phantom process monitor daemon
rish -c "settings put global settings_enable_monitor_phantom_procs false"
```
This configuration survives across reboots on modern Android versions, allowing the controller to maintain persistent background daemons, queue listeners, and multi-step ReAct loops indefinitely.

---

## Roadblock 3: Samsung OneUI Continuous Volume Slider vs Discrete 15-Step Audio Setting

### Symptom
When a user issued a command like `"set volume to 80%"`, three compounding failures occurred:
1. Using naive keyevents (`input keyevent 24` for Volume Up) required firing multiple pulses, adjusting volume by only ~6.6% per pulse and triggering a large, floating Samsung OneUI volume slider overlay that obstructed the right 30% of the display for 3.0 seconds, occluding underlying buttons during `uiautomator` screen capture.
2. In text parsing logic, testing `elif "0%" in prompt` prior to integer regex extraction caused `"80%"` and `"90%"` to match `"0%"` (since `"0%"` is a literal substring of `"80%"`), mistakenly setting the device volume to complete mute (`0%`)!
3. Sending raw percentage values (e.g. `80`) to system settings failed because Samsung OneUI audio hardware gain operates on a discrete 0–15 scale rather than 0–100.

### Root Cause
- Samsung OneUI's `AudioService` binds `STREAM_MUSIC` (Stream 3) strictly to **16 discrete integer levels (indices 0 through 15)**.
- Standard AOSP continuous scaling does not apply to Samsung's discrete hardware gain table.
- Firing repetitive physical keyevents renders the floating volume slider HUD on the top-level window layer (`TYPE_STATUS_BAR_SUB_PANEL`).

### Engineering Solution: Mathematical Quantization & Direct AudioService Binder Calls
1. **Regex Priority Parsing:** Rewrote prompt parsing to extract explicit numeric percentages via regular expressions (`r"\b(\d{1,3})%"`) before evaluating relative keyword matches.
2. **Discrete Quantization Formula:** Implemented exact integer mapping to OneUI's 15-step scale:
   $$\text{target\_idx} = \text{clamp}\left(0, 15, \text{round}\left(\frac{\text{percentage} \times 15}{100}\right)\right)$$
   For 80%: $\text{round}(80 \times 15 / 100) = \text{round}(12.0) = \mathbf{12}$.
3. **Direct AudioService Dispatch:** Replaced synthetic keyevents with direct system binder calls:
   ```bash
   cmd media_session volume --stream 3 --set 12
   ```
   This updates the audio amplifier instantly **without triggering the floating UI volume slider overlay**, leaving the screen unobstructed for visual hierarchy dumps.

---

## Roadblock 4: Single Provider Rate Limits (HTTP 429) & Model Outages

### Symptom
During complex compound missions (such as checking battery, adjusting volume, launching YouTube, and searching for a specific video), the agent executes multiple perception, planning, and verification cycles. Under rapid testing:
- Free-tier API keys hit provider rate limits (`HTTP 429 Too Many Requests`).
- Cloud endpoints occasionally returned `HTTP 402 Payment Required` or model retirement errors (`HTTP 404 Model Deprecated`).
- A single rate-limited request crashed the entire agent mission.

### Root Cause
Modern agentic workflows require 5 to 15 LLM inferences per compound task. Standard single-account developer tiers impose strict RPM (Requests Per Minute) and TPM (Tokens Per Minute) ceilings that are easily exceeded during rapid ReAct cycles.

### Engineering Solution: 19-Key 3-Tier Automated Failover Architecture
We engineered an automated key rotation and cascading engine (`rotate_keys.py` and `query_llm_resilient` in `master_agent.py`):
1. **19 Independent Keys across 3 Tiers:**
   - **Tier 1 (7 Keys):** Primary Low-Latency Flash API endpoints for deep planning and structured JSON diagnostics.
   - **Tier 2 (5 Keys):** Groq LPU high-speed inference for sub-300ms reflex classification.
   - **Tier 3 (7 Keys):** OpenRouter fallback pool for global high-diversity failover.
2. **Transparent Interception & Backoff:** The engine intercepts `HTTP 429`, `402`, `404`, and socket timeouts, immediately advancing the round-robin pointer:
   $$\text{index} = (\text{index} + 1) \pmod{\text{len(keys)}}$$
   with exponential backoff and jitter:
   $$\text{delay} = \min(\text{delay} \times 1.5, 4.0)$$
3. **Cross-Tier Cascading:** If Tier 1 keys are exhausted, the request cascades automatically to Tier 2, and subsequently to Tier 3, providing up to **38 consecutive retry attempts** and guaranteeing zero-downtime execution.

---

## Roadblock 5: Intent Collision & URL Interceptor Disambiguation Dialogs

### Symptom
When attempting to open a URL or execute an intent via standard Android commands:
```bash
am start -a android.intent.action.VIEW -d "https://www.youtube.com/watch?v=..."
```
Android displayed a modal system disambiguation dialog: *"Open with YouTube, Chrome, or Samsung Internet?"* with options "Just Once" and "Always". The agent stalled indefinitely because the target video never loaded.

### Root Cause
Android's `IntentResolver` checks all registered broadcast receivers and intent filters matching the MIME type and URL scheme. If multiple browsers or media handlers are installed and the user has not established a default handler, the system suspends intent execution and displays the modal chooser.

### Engineering Solution: Explicit Package Targeting (`-p <package>`)
1. **Explicit Package Dispatch:** In the planner, all intent-based sub-tasks specify the exact target application package:
   ```bash
   am start -p app.revanced.android.youtube -a android.intent.action.VIEW -d "https://..."
   ```
   Explicitly specifying `-p <package>` bypasses the Android `IntentResolver` chooser completely, launching the target application immediately without modal dialogs.
2. **Dynamic Package Discovery Fallback:** If the primary package is not installed on the device, the agent dynamically queries `pm list packages | grep -i <app>`, detects alternative installed packages (such as `com.google.android.youtube` or `com.android.chrome`), and falls back to visual UI search navigation.

---

## Roadblock 6: The Bash Reserved Keyword Conflict (`alias do=...`)

### Symptom
When configuring shell environments for one-tap execution, defining convenience aliases caused Termux startup to abort with:
```bash
bash: syntax error near unexpected token 'do'
```

### Root Cause
In POSIX shell and Bash grammars, `do` is a reserved language keyword used strictly in loop constructs (`for ...; do ... done`). Defining an alias or function named `do` violates lexical grammar rules.

### Engineering Solution: Standalone POSIX Executables (`$PREFIX/bin/ai`)
Rather than relying on shell aliases, we deployed standalone POSIX binary scripts placed directly into the user's `$PREFIX/bin/` path:
- `$PREFIX/bin/ai` (POSIX wrapper script launching `master_agent.py "$@"`)
- `$PREFIX/bin/agent` (Fast intent dispatcher)
This provides clean, zero-boilerplate CLI usage (`ai "set volume 50%"`) without polluting shell configurations or risking keyword collisions.

---

## Roadblock 7: Terminal Visibility Loss (The "Navigated Away" Problem)

### Symptom
When a user triggered an automation mission in Termux that opened another application (e.g. YouTube or Settings), Android's window manager brought the target application to the foreground. The user could no longer see the terminal output and had no way of knowing what the agent was doing, whether it was verifying state, or if an error had occurred.

### Root Cause
Android's standard window manager enforces single-foreground application display. Minimizing Termux hides all terminal stdout/stderr streams from view.

### Engineering Solution: Multi-Layered Feedback Architecture
1. **Android Notification Shade Live HUD:** The agent posts real-time progress updates directly into Android's notification drawer using:
   ```bash
   cmd notification post -S bigtext -t "Agent Controller" live_hud "Step 2/3: Launching YouTube and verifying playback..."
   ```
   Users simply swipe down the notification shade from within any app to check real-time agent status.
2. **Dual-Stream Execution Logging (`ai log`):** A custom `TeeLogger` streams all console output to `/sdcard/agent/last_run.log`. Executing `ai log` at any time displays the complete transcript, reasoning steps, and verification evidence of the previous run.
3. **Pop-up Floating Window Support:** Samsung OneUI supports running Termux in native **Pop-up View**, allowing the terminal to float as an interactive transparent window over the automated application.

---

## Roadblock 8: Subprocess Multilingual Non-ASCII Encoding on Windows

### Symptom
When running the controller remotely from a Windows PC, missions containing non-ASCII prompts (such as Bengali বাংলা, Hindi हिंदी, or emoji characters) crashed with:
```
UnicodeEncodeError: 'cp1252' codec can't encode character '\u09ac' in position ...
```

### Root Cause
Windows console and Python's default `subprocess.run()` inherit the active Windows ANSI code page (`cp1252`), which cannot represent Indic scripts or Unicode emoji.

### Engineering Solution: Strict UTF-8 Stream Reconfiguration
We enforced UTF-8 across all Python subprocess and console streams:
```python
import sys, subprocess

# Reconfigure stdout and stderr for UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# Force explicit UTF-8 in subprocess execution
subprocess.run(cmd, shell=True, capture_output=True, encoding="utf-8", errors="replace")
```

---

## Roadblock 9: Isolated Multi-User Profiles (Dual Messenger / Secure Folder)

### Symptom
Querying installed packages via `pm list packages` occasionally returned security warnings:
```
Error: java.lang.SecurityException: Shell does not have permission to access user 150
```

### Root Cause
Samsung OneUI creates isolated secondary user profiles (`user 150` or `user 95`) for Dual Messenger and Secure Folder applications. Standard shell (UID 2000) does not possess cross-user management permissions without explicit profile arguments.

### Engineering Solution: Primary Profile (`u0`) Package Filtering
Added error-tolerant parsing to package discovery routines, filtering queries to the primary user profile (`--user 0`) and gracefully discarding permission warnings from sandboxed sub-profiles.

---

## Roadblock 10: Identity Misclassification & The Conversational Self-Search Loop

### Symptom
When asked a conversational question like `"ai who are you"` or `"ai what capabilities do you have"`, early agent versions performed a web search on Google for *"Antigravity Master Android Autonomous Controller"* and returned a generic marketing snippet scraped from the web.

### Root Cause
The task decomposition schema only defined device manipulation actions (`volume`, `media`, `whatsapp`, `youtube`, `search`). When presented with a purely conversational query, the model attempted to satisfy the prompt using the closest available action, misclassifying questions about its own identity as external web searches.

### Engineering Solution: Dedicated Conversational `chat` Action
Added a first-class `chat` action to the task decomposition schema. Conversational questions, status queries, hardware explanations, and general knowledge questions are answered directly and concisely by the model without dispatching external web searches against itself.

---

*Authored by the Autonomous Android Controller Engineering Team.*
*Licensed under the Apache License, Version 2.0.*
