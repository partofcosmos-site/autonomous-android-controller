#!/usr/bin/env bash
# ==========================================================
# Autonomous Android Controller One-Tap Mobile Summoner
# Supports English, Bengali (বাংলা), Hindi (हिंदी)
# ==========================================================

# Ensure UTF-8 character encoding for multilingual support without setlocale warnings
if [ -z "$LANG" ] || [ "$LANG" = "C" ]; then
    export LANG="C.UTF-8"
fi
if locale -a 2>/dev/null | grep -qi "^en_US\.utf"; then
    export LC_ALL="en_US.UTF-8"
elif [ -z "$LC_ALL" ] || [ "$LC_ALL" = "C" ]; then
    export LC_ALL="C.UTF-8"
fi

# Locate master_agent.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/master_agent.py" ]; then
    MASTER_AGENT="$SCRIPT_DIR/master_agent.py"
elif [ -f "/sdcard/agent/master_agent.py" ]; then
    MASTER_AGENT="/sdcard/agent/master_agent.py"
else
    MASTER_AGENT="master_agent.py"
fi

# Resolve Python 3 executable across environments
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

# Immediate Help Flag Handling (-h, --help, help)
if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ "$1" = "help" ]; then
    echo "Usage: summon_agent.sh [mission]"
    echo ""
    echo "Options:"
    echo "  -h, --help, help    Show this help message and exit"
    echo ""
    echo "Examples:"
    echo "  summon_agent.sh \"Set volume to 80% and play Kishore Kumar on YouTube\""
    echo "  summon_agent.sh \"বাংলায় গান চালাও\""
    exit 0
fi

# Helper function to detect Termux mobile environment
is_termux() {
    [ -n "$TERMUX_VERSION" ] || [[ "${PREFIX:-}" == *"com.termux"* ]]
}

# Input acquisition: Direct arguments vs Interactive prompt/dialog
if [ -n "$1" ]; then
    TEXT="$*"
else
    if is_termux && command -v termux-dialog >/dev/null 2>&1; then
        PROMPT=$(termux-dialog text -t "Autonomous Android Controller" -i "Speak or type your command in English, Bengali, Hindi...")
        if command -v jq >/dev/null 2>&1; then
            TEXT=$(echo "$PROMPT" | jq -r '.text // empty' 2>/dev/null)
        else
            TEXT=$(echo "$PROMPT" | sed -n 's/.*"text"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
        fi
    else
        read -r -p "Enter mission (English/বাংলা/हिंदी): " TEXT
    fi
fi

# Mission dispatch
if [ -n "$TEXT" ]; then
    if [ "$TEXT" = "-h" ] || [ "$TEXT" = "--help" ] || [ "$TEXT" = "help" ]; then
        echo "Usage: summon_agent.sh [mission]"
        exit 0
    fi
    echo "[+] Executing Mission: $TEXT"
    "$PYTHON_BIN" "$MASTER_AGENT" "$TEXT"
else
    echo "[-] Cancelled or empty input."
fi
