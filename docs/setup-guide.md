# Setup & User Operation Guide

---

## 1. Introduction & Operating Models

The **Autonomous Android Controller** is engineered to run in two distinct operating modes:
1. **Standalone Mobile Execution (100% On-Device):** The agent runs locally inside **Termux** on your Android device, invoking system shell commands and UI automation directly via **Shizuku (`rish`)** under rootless `UID 2000`. No host PC, cables, or external servers required after initial setup.
2. **PC Remote Control Execution (Host Workstation):** The agent runs on a host PC (Windows, macOS, or Linux) running Python 3.10+, controlling the target Android device over standard **Wireless ADB** or USB tethering.

Both modes leverage the exact same core controller logic, 19-key multi-provider failover engine, and closed-loop ReAct diagnostic system.

---

## 2. Prerequisites & System Requirements

### Target Android Device Requirements
- **Operating System:** Android 11.0 (API 30) or higher (Android 14 with Samsung OneUI 6.x / 7.0 recommended).
- **Target Hardware Baseline:** Tested and optimized on the **Samsung Galaxy M56 (`SM-M566B`)** (ARM64 architecture).
- **Networking:** Local Wi-Fi network connection (required once for initial Wireless Debugging pairing).
- **Installed Applications:**
  - **Shizuku:** Rootless system API service (Install from Google Play Store or GitHub releases).
  - **Termux:** Terminal emulator environment (Install from F-Droid or GitHub; do *not* use Google Play version as it is deprecated).

### Host PC Requirements (Optional for PC Remote Mode)
- **Python:** Python 3.10 or higher.
- **Platform Tools:** Android SDK Platform-Tools (`adb`) added to system `PATH`.
- **Operating System:** Windows 10/11, macOS, or Linux.

---

## 3. Shizuku Setup: Rootless Privilege Escalation (`UID 2000`)

Shizuku bridges standard userland applications into Android's native `UID 2000` (`shell`) privilege domain without requiring device rooting, bootloader unlocking, or tripping SafetyNet / Play Integrity attestation.

### Step 1: Enable Developer Options
1. Open device **Settings** $\rightarrow$ **About phone** $\rightarrow$ **Software information**.
2. Tap **Build number** 7 times until you see the toast message: *"Developer mode has been enabled."*
3. Enter your device lock-screen PIN or password when prompted.

### Step 2: Enable Wireless Debugging
1. Navigate to **Settings** $\rightarrow$ **Developer options**.
2. Scroll down to the **Debugging** section.
3. Toggle **Wireless debugging** to **ON**.
4. Confirm the prompt by checking *"Always allow on this network"* and tapping **Allow**.

### Step 3: Pair Shizuku via Wireless Debugging
1. Open the **Shizuku** application.
2. Under the **Start via Wireless Debugging** section, tap **Pairing**.
3. Tap **Developer options** to open the system split-screen or notification drawer.
4. In **Developer options** $\rightarrow$ **Wireless debugging**, tap **Pair device with pairing code**.
5. Note the 6-digit Wi-Fi pairing code and port displayed on the screen.
6. Pull down the Android notification shade, locate the **Shizuku Pairing Service** prompt, enter the 6-digit pairing code, and tap **Send**.
7. Confirm the toast notification: *"Pairing successful."*

### Step 4: Start the Shizuku Service
1. Return to the **Shizuku** app.
2. Under **Start via Wireless Debugging**, tap **Start**.
3. The screen will display terminal output as Shizuku starts its internal Binder server.
4. Verify the top status banner displays: **"Shizuku is running (Version ... / UID 2000)"**.

### Step 5: Export the `rish` CLI Bridge
1. Inside Shizuku, tap the **Use Shizuku in terminal apps** card.
2. Tap **Export files**.
3. Choose a folder or copy the exported `rish` and `rish.dex` binaries to Termux:
   ```bash
   # From within Termux:
   curl -sSL https://raw.githubusercontent.com/RikkaApps/Shizuku-API/master/rish/rish -o $PREFIX/bin/rish
   curl -sSL https://raw.githubusercontent.com/RikkaApps/Shizuku-API/master/rish/rish.dex -o $PREFIX/bin/rish.dex
   chmod +x $PREFIX/bin/rish
   ```
4. Verify rootless shell access by running:
   ```bash
   rish -c "id"
   ```
   **Expected Output:**
   ```
   uid=2000(shell) gid=2000(shell) groups=2000(shell),1004(input),1007(log)...
   ```

---

## 4. Standalone Mobile Setup (Inside Termux)

### Step 1: Update Termux Package Repositories
Launch Termux and execute:
```bash
pkg update -y && pkg upgrade -y
```

### Step 2: Install Core Dependencies
Install Python, Git, and underlying C build libraries:
```bash
pkg install -y python git clang libxml2 libxslt libffi openssl
```

### Step 3: Install Required Python Packages
Install Python HTTP requests and testing frameworks:
```bash
pip install --upgrade pip
pip install requests pytest
```

### Step 4: Clone or Copy Repository
Clone the repository into your local Termux home directory or `/sdcard/agent`:
```bash
cd $HOME
git clone https://github.com/partofcosmos-site/autonomous-android-controller.git
cd autonomous-android-controller
```

### Step 5: Configure Environment Variables (`.env`)
Create your active `.env` file from the provided `.env.example` template:
```bash
cp .env.example .env
nano .env
```
Populate your active API keys:
- `PRIMARY_FLASH_KEY_1` through `PRIMARY_FLASH_KEY_7` (Tier 1 Flash keys)
- `GROQ_API_KEY_1` through `GROQ_API_KEY_5` (Tier 2 Groq keys)
- `OPENROUTER_API_KEY_1` through `OPENROUTER_API_KEY_7` (Tier 3 OpenRouter keys)

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

### Step 6: Install Global `ai` CLI Executable
To run missions with zero boilerplate from anywhere in Termux, install the executable wrapper:
```bash
cp ai $PREFIX/bin/ai
chmod +x $PREFIX/bin/ai
```

Verify the installation:
```bash
ai --help
```

---

## 5. PC Remote Control Setup (Wireless ADB)

If you prefer controlling your Android device from a Windows, macOS, or Linux workstation:

### Step 1: Clone Repository on Host PC
```bash
git clone https://github.com/partofcosmos-site/autonomous-android-controller.git
cd autonomous-android-controller
```

### Step 2: Set Up Python Virtual Environment
```bash
# On Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# On Linux / macOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Connect via Wireless ADB
1. On the Android device, verify **Wireless Debugging** is enabled in Developer Options.
2. Note the device IP address and port (e.g. `<DEVICE_IP>:<PORT>`).
3. On your host PC, establish the ADB connection:
   ```bash
   adb connect <DEVICE_IP>:<PORT>
   ```
4. Verify the connected device:
   ```bash
   adb devices
   ```
   *Expected Output:*
   ```
   List of devices attached
   <DEVICE_IP>:<PORT>    device
   ```

### Step 4: Configure Host `.env`
Copy the environment template and insert your keys:
```bash
cp .env.example .env
```

### Step 5: Execute via PC CLI
Run missions using the Windows batch wrapper or direct Python:
```bash
# Windows Command Prompt / PowerShell
.\ai.cmd "set volume to 70% and open YouTube"

# Linux / macOS / Direct Python
python master_agent.py "set volume to 70% and open YouTube"
```

---

## 6. Disabling Android Phantom Process Killer (Permanent Bypass)

On Android 12, 13, and 14, the operating system enforces a 32-child-process limit on background applications. When Termux spawns sub-processes, the system killer may terminate them unexpectedly.

Execute the following commands once via `rish` or `adb shell` to permanently disable phantom process throttling:

```bash
# Increase max phantom processes to 32-bit integer ceiling
rish -c "device_config put activity_manager max_phantom_processes 2147483647"

# Disable monitor daemon
rish -c "settings put global settings_enable_monitor_phantom_procs false"
```
*(If running from PC via ADB, substitute `rish -c` with `adb shell`)*.

---

## 7. Command Usage Guide

### Natural Language Missions
```bash
# Hardware volume and media control
ai "set volume to 80% and play Kishore Kumar on YouTube"

# Messaging automation (self-addressed verification)
ai "open WhatsApp and message +15551234567 saying meeting started"

# Browser control & navigation
ai "open Firefox and switch to private browsing"

# System settings manipulation
ai "set screen brightness to 50%"
```

### Multilingual Prompts
The controller parses English, Bengali (বাংলা), and Hindi (हिंदी):
```bash
# Bengali
ai "volume 70 percent koro ebong gaan chalao"

# Hindi
ai "aawaz 80 percent badhao aur gaana lagao"
```

### Conversational Intelligence
Query device specifications, controller capabilities, or status directly without triggering external web searches:
```bash
ai "who are you"
ai "what capabilities do you have"
ai "explain Samsung OneUI volume quantization"
```

### Real-Time HUD & Transcript Logs
- **Android Notification Shade HUD:** Pull down the notification drawer during mission execution to view live status updates (`cmd notification post`).
- **Review Previous Run Log:**
  ```bash
  ai log
  ```
- **Interactive Terminal Summoner:**
  ```bash
  ./summon_agent.sh
  ```

---

## 8. Troubleshooting & Common Setup Hurdles

### Issue 1: `rish: command not found`
- **Cause:** The `rish` binary was not copied into `$PREFIX/bin` or lacks execute permissions.
- **Solution:** Verify `which rish`. If missing, copy `rish` and `rish.dex` into `/data/data/com.termux/files/usr/bin/` and run `chmod 755 $PREFIX/bin/rish`.

### Issue 2: `Permission denied` when running `rish`
- **Cause:** Shizuku is not running or Termux has not been authorized.
- **Solution:** Open the Shizuku app. If it says "Shizuku is not running", tap **Start via Wireless Debugging**. Tap **Authorized Applications** inside Shizuku and ensure Termux is toggled ON.

### Issue 3: Wireless Debugging Disconnects After Reboot
- **Cause:** Android OS randomizes the Wireless Debugging port upon device restart.
- **Solution:** Reconnecting to your known Wi-Fi network re-enables Wireless Debugging automatically on Samsung devices. Open Shizuku and tap **Start via Wireless Debugging**. Re-pairing with a PIN code is *not* required—only tapping Start.

### Issue 4: Termux Terminated in Background
- **Cause:** Samsung OneUI Device Care battery optimizations sleeping background processes.
- **Solution:**
  1. Open device **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Termux** $\rightarrow$ **Battery** $\rightarrow$ select **Unrestricted**.
  2. Open device **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Shizuku** $\rightarrow$ **Battery** $\rightarrow$ select **Unrestricted**.
  3. In the Recent Apps screen, tap the Termux app icon and select **Lock this app**.

### Issue 5: Windows PowerShell Encoding Error on Non-ASCII Prompts
- **Cause:** Windows console defaulting to `cp1252` encoding when processing Bengali, Hindi, or emojis.
- **Solution:** Set console code page to UTF-8 before running:
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  chcp 65001
  ```

---

*Authored by the Autonomous Android Controller Engineering Team.*
*Licensed under the Apache License, Version 2.0.*
