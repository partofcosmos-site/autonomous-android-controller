#!/bin/bash
# ==============================================================================
# God-Mode Autonomous Daemon Launcher (start_god_mode.sh)
# Target: Samsung Galaxy M56 (SM-M566B) | Exynos 1480 | OneUI 8.5
# Runs headless background daemon via Shizuku (UID 2000) or ADB shell.
# Listens for autonomous instructions without requiring an interactive session.
# ==============================================================================

set -e

PORT="${GOD_DAEMON_PORT:-5005}"
HOST="${GOD_DAEMON_HOST:-0.0.0.0}"

# Resolve Storage & Directory
if [ -d "/sdcard/agent" ]; then
    AGENT_DIR="/sdcard/agent"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    AGENT_DIR="$(dirname "$SCRIPT_DIR")"
fi

PID_FILE="$AGENT_DIR/god_daemon.pid"
LOG_FILE="$AGENT_DIR/god_daemon.log"
DAEMON_SCRIPT="$AGENT_DIR/god_daemon.py"

if [ ! -f "$DAEMON_SCRIPT" ]; then
    if [ -f "$AGENT_DIR/scripts/god_daemon.py" ]; then
        DAEMON_SCRIPT="$AGENT_DIR/scripts/god_daemon.py"
    else
        echo "[-] Error: god_daemon.py not found at $DAEMON_SCRIPT"
        exit 1
    fi
fi

# Resolve Python Binary
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

echo "=================================================================="
echo "⚡ Starting Shizuku God-Mode Autonomous Background Daemon"
echo "=================================================================="
echo "📍 Storage Root:  $AGENT_DIR"
echo "📍 Daemon Script: $DAEMON_SCRIPT"
echo "📍 HTTP Port:     $PORT"

# 1. Check if already running and healthy
if [ -f "$PID_FILE" ]; then
    EXISTING_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "[*] Daemon process already alive (PID: $EXISTING_PID)."
        if curl -s -m 2 "http://127.0.0.1:$PORT/health" | grep -q '"status":\s*"ok"' 2>/dev/null; then
            echo "[+] God-Mode daemon is already RUNNING and HEALTHY at http://127.0.0.1:$PORT"
            exit 0
        fi
        echo "[!] Process alive but HTTP endpoint unresponsive. Restarting..."
        kill -9 "$EXISTING_PID" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
fi

# 2. Launch headless background process detached from terminal
echo "[+] Spawning background daemon detached from terminal session..."
mkdir -p "$AGENT_DIR/daemon_queue"
mkdir -p "$AGENT_DIR/screenshots"

nohup "$PYTHON_BIN" "$DAEMON_SCRIPT" --daemon --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
DAEMON_PID=$!
echo "$DAEMON_PID" > "$PID_FILE"
echo "[+] Process launched with PID: $DAEMON_PID"

# 3. Wait and verify health endpoint
echo -n "[*] Awaiting daemon readiness"
READY=0
for i in $(seq 1 10); do
    sleep 0.8
    if curl -s -m 2 "http://127.0.0.1:$PORT/health" | grep -q '"status":\s*"ok"' 2>/dev/null; then
        READY=1
        break
    fi
    echo -n "."
done
echo ""

if [ "$READY" -eq 1 ]; then
    echo "=================================================================="
    echo "✅ God-Mode Autonomous Daemon is ONLINE & LISTENING"
    echo "=================================================================="
    echo "🌐 API Endpoint:  http://127.0.0.1:$PORT"
    echo "🆔 Process PID:   $DAEMON_PID"
    echo "📂 Logs:          $LOG_FILE"
    echo "📂 IPC Queue:     $AGENT_DIR/daemon_queue"
    echo ""
    echo "Superpower Endpoints Ready:"
    echo "  - POST /tap                    {\"x\": int, \"y\": int}"
    echo "  - POST /swipe                  {\"x1\": int, \"y1\": int, \"x2\": int, \"y2\": int}"
    echo "  - POST /type                   {\"text\": \"...\"}"
    echo "  - POST /key                    {\"code\": \"BACK\" | 4}"
    echo "  - POST /notifications/expand   (Expand statusbar)"
    echo "  - POST /notifications/collapse (Collapse statusbar)"
    echo "  - POST /quick_settings         (Expand Quick Settings)"
    echo "  - POST /screenshot             {\"path\": \"...\"}"
    echo "  - GET  /state                  (Telemetry & focused app)"
    echo "  - POST /instruction            {\"instruction\": \"autonomous mission\"}"
    echo "=================================================================="

    # Post Android notification if running on device
    if command -v cmd >/dev/null 2>&1; then
        cmd notification post -S bigtext -t "⚡ God-Mode Daemon Active" "AgentDaemon" "Listening on port $PORT (UID 2000 / Shizuku). Interactive session not required." >/dev/null 2>&1 || true
    fi
    exit 0
else
    echo "[-] Warning: Daemon started (PID $DAEMON_PID) but health check did not respond within 8s."
    echo "[-] Inspect logs at: $LOG_FILE"
    cat "$LOG_FILE" | tail -n 20
    exit 1
fi
