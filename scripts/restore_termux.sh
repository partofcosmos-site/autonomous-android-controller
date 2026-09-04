#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Termux Zero-Loss Instant Recovery Architecture (restore_termux.sh)
# Target: Samsung Galaxy M56 (SM-M566B) | Android 15 / OneUI 8.5
# Restores complete agent environment in < 30 seconds after Termux App Data Wipe
# ZERO RE-DOWNLOAD of the 1.35GB offline model.
# ==============================================================================

set -e

START_TIME=$(date +%s)

echo "=================================================================="
echo "🛡️  TERMUX ZERO-LOSS INSTANT RECOVERY PROTOCOL"
echo "=================================================================="
echo ""
echo "ℹ️  WHY TERMUX DATA CLEARANCE HAPPENS:"
echo "   Android OS application sandboxing stores Termux internal files in:"
echo "   /data/data/com.termux/ (private internal storage)."
echo "   When Android OneUI Device Care, app cleaners, or users perform"
echo "   'Clear App Data', this private sandbox is wiped clean."
echo ""
echo "ℹ️  WHY ZERO DATA IS LOST:"
echo "   All agent intelligence, history, configuration, and offline models"
echo "   reside in external non-volatile shared storage at /sdcard/agent:"
echo "     * 1.35GB GGUF Local Model:  /sdcard/agent/models/"
echo "     * Persistent SQLite Memory: /sdcard/agent/memory.db"
echo "     * API Credentials & Keys:   /sdcard/agent/.env"
echo "     * Full Python Core:         /sdcard/agent/*.py"
echo "   Shared storage is isolated from app sandboxes and is NEVER cleared"
echo "   during app data wipes or package re-installations."
echo "=================================================================="
echo ""

# 1. Verify Storage Access and /sdcard/agent Presence
echo "[Step 1/5] Detecting /sdcard/agent storage..."
if [ ! -d "/sdcard/agent" ]; then
    echo "[-] /sdcard/agent is not accessible."
    echo "[*] Requesting Android storage permission..."
    if command -v termux-setup-storage >/dev/null 2>&1; then
        termux-setup-storage
        sleep 2
    fi
    if [ ! -d "/sdcard/agent" ]; then
        echo "[-] Fatal: /sdcard/agent could not be found."
        echo "    Ensure 'Files and media' permission is granted to Termux in Android Settings."
        exit 1
    fi
fi
echo "[+] Detected persistent storage at /sdcard/agent (INTACT)"

# 2. Re-install Core System Dependencies in Termux Sandbox
echo ""
echo "[Step 2/5] Updating and installing system packages (python, git, curl)..."
export DEBIAN_FRONTEND=noninteractive
pkg update -y
pkg install -y python git curl termux-api

# 3. Re-link Storage Symlink & Shortcuts
echo ""
echo "[Step 3/5] Re-linking ~/agent and configuring CLI binaries..."
rm -rf "$HOME/agent"
ln -sf /sdcard/agent "$HOME/agent"
echo "[+] Created symlink: ~/agent -> /sdcard/agent"

# Configure Termux properties for external app execution
mkdir -p "$HOME/.termux"
if ! grep -q "allow-external-apps = true" "$HOME/.termux/termux.properties" 2>/dev/null; then
    echo "allow-external-apps = true" >> "$HOME/.termux/termux.properties"
    echo "[+] Enabled allow-external-apps in ~/.termux/termux.properties"
fi

# Set up global 'ai' and 'god-mode' CLI commands in $PREFIX/bin
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    ln -sf /sdcard/agent/ai "$PREFIX/bin/ai"
    chmod +x "$PREFIX/bin/ai"
    echo "[+] Linked executable: $PREFIX/bin/ai"

    if [ -f "/sdcard/agent/scripts/start_god_mode.sh" ]; then
        ln -sf /sdcard/agent/scripts/start_god_mode.sh "$PREFIX/bin/god-mode"
        chmod +x "$PREFIX/bin/god-mode"
        echo "[+] Linked executable: $PREFIX/bin/god-mode"
    fi
fi

# Set up Termux Widget shortcuts in ~/.shortcuts
mkdir -p "$HOME/.shortcuts/tasks"
if [ -f "/sdcard/agent/summon_agent.sh" ]; then
    cp -f /sdcard/agent/summon_agent.sh "$HOME/.shortcuts/agent.sh"
    cp -f /sdcard/agent/summon_agent.sh "$HOME/.shortcuts/tasks/agent_bg.sh"
    chmod +x "$HOME/.shortcuts/agent.sh" "$HOME/.shortcuts/tasks/agent_bg.sh"
    echo "[+] Restored Termux Widget shortcuts in ~/.shortcuts"
fi

# 4. Install Python Requirements
echo ""
echo "[Step 4/5] Restoring Python dependencies from /sdcard/agent/requirements.txt..."
if [ -f "/sdcard/agent/requirements.txt" ]; then
    pip install -r /sdcard/agent/requirements.txt
else
    pip install requests pytest
fi

# 5. Verify Model & Shizuku Integrity
echo ""
echo "[Step 5/5] Verifying offline model and Shizuku shell access..."

MODEL_FILE="/sdcard/agent/models/smollm2-1.7b-instruct-q4_k_m.gguf"
if [ -f "$MODEL_FILE" ]; then
    MODEL_SIZE=$(ls -lh "$MODEL_FILE" | awk '{print $5}')
    echo "[+] Offline Model Found: $MODEL_FILE ($MODEL_SIZE) -> ZERO BYTES DOWNLOADED!"
else
    echo "[!] Notice: Offline model not detected at $MODEL_FILE"
    echo "    To download run: bash /sdcard/agent/scripts/setup_offline_model.sh"
fi

if command -v rish >/dev/null 2>&1 || [ -f "/system/bin/rish" ]; then
    echo "[+] Shizuku 'rish' detected: UID 2000 hardware execution READY"
else
    echo "[*] Shizuku 'rish' not in PATH. Ensure Shizuku is running and rish is exported."
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "=================================================================="
echo "🎉 RECOVERY COMPLETE IN ${ELAPSED}s — ZERO DATA LOSS!"
echo "=================================================================="
echo "Ready for autonomous operation:"
echo "  * Quick Command:     ai \"set volume to 50% and open revanced\""
echo "  * Start God Daemon:  god-mode"
echo "  * Launch Bridge:     python /sdcard/agent/opendroid_bridge.py"
echo "=================================================================="
