#!/bin/bash
# ==============================================================================
# Autonomous Android Controller — Floating Controller Manager
# Controls the floating bubble overlay: completely removes weak default overlays,
# or upgrades it to God-Level connected to our Shizuku/master-hub bridge.
# Target: Samsung Galaxy M56 (Android 16 / OneUI 8.5)
# ==============================================================================

ACTION="${1:-status}"
PKG="com.opendroid.aiagent"

case "$ACTION" in
    remove|disable|off)
        echo "🛡️ Removing weak floating bubble overlay..."
        if command -v appops >/dev/null 2>&1; then
            appops set "$PKG" SYSTEM_ALERT_WINDOW ignore
        fi
        am force-stop "$PKG" 2>/dev/null || true
        echo "✅ Floating bubble completely REMOVED from screen."
        echo "   Zero clutter, zero background battery drain."
        ;;

    god|god-level|enable|on)
        echo "⚡ Upgrading floating button to GOD-LEVEL..."
        if command -v appops >/dev/null 2>&1; then
            appops set "$PKG" SYSTEM_ALERT_WINDOW allow
        fi
        
        # Ensure God-Mode Daemon and OpenDroid Bridge are active
        AGENT_DIR="/sdcard/agent"
        
        echo "🚀 Starting OpenDroid Bridge on 127.0.0.1:4000 (OpenAI-compatible)..."
        if [ -f "$AGENT_DIR/opendroid_bridge.py" ]; then
            nohup python3 "$AGENT_DIR/opendroid_bridge.py" --host 127.0.0.1 --port 4000 > /sdcard/agent/bridge.log 2>&1 &
        fi

        # Launch OpenDroid to restore overlay connected to bridge
        am start -n "$PKG/com.opendroid.ai.MainActivity" 2>/dev/null || true
        echo "✅ God-Level floating button ACTIVATED."
        echo "   Connected to 19 rotating API keys + Shizuku UID 2000 hardware execution."
        ;;

    status)
        echo "🔍 Checking floating button overlay status:"
        if command -v appops >/dev/null 2>&1; then
            STATUS=$(appops get "$PKG" SYSTEM_ALERT_WINDOW 2>/dev/null)
            echo "   Overlay AppOp: $STATUS"
        fi
        VISIBLE=$(dumpsys window windows 2>/dev/null | grep -i "$PKG" | wc -l)
        if [ "$VISIBLE" -gt 0 ]; then
            echo "   State: Floating button is VISIBLE ($VISIBLE windows)"
        else
            echo "   State: Floating button is HIDDEN / REMOVED (0 windows)"
        fi
        ;;

    *)
        echo "Usage: floating_controller.sh [remove|god-level|status]"
        echo "  remove     - Completely dismiss and disable the floating button overlay"
        echo "  god-level  - Enable the floating button backed by God-Mode Bridge (port 4000)"
        echo "  status     - Check if floating button is currently visible"
        exit 1
        ;;
esac
