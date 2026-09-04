#!/bin/bash
# Autonomous Android Controller — 1-Tap Offline AI Daemon Launcher
# Target: Samsung Galaxy M56 (Exynos 1480, OneUI 8.5)

MODEL_DIR="/sdcard/agent/models"
MODEL_FILE="$MODEL_DIR/smollm2-1.7b-instruct-q4_k_m.gguf"
MODEL_URL="https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/resolve/main/smollm2-1.7b-instruct-q4_k_m.gguf"
GRAMMAR_FILE="/sdcard/agent/grammars/action.gbnf"
LOG_FILE="/sdcard/agent/llama_server.log"
PORT=8080

echo "🤖 [Autonomous Controller] Checking Local Offline AI status..."

# 1. Check if already running
if curl -s "http://127.0.0.1:$PORT/health" | grep -q "ok\|true\|status" 2>/dev/null; then
    echo "✅ Local Offline AI server is already RUNNING on http://127.0.0.1:$PORT"
    exit 0
fi

# 2. Check model file
if [ ! -f "$MODEL_FILE" ]; then
    echo "📥 Downloading SmolLM2-1.7B-Instruct (Q4_K_M) GGUF..."
    mkdir -p "$MODEL_DIR"
    curl -L -C - -o "$MODEL_FILE" "$MODEL_URL"
fi

# 3. Check for llama-server binary
if ! command -v llama-server >/dev/null 2>&1; then
    echo "⚠️ llama-server not found in PATH."
    echo "👉 Install in Termux via: pkg install -y clang cmake git && git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && cmake -B build && cmake --build build --config Release"
    exit 1
fi

# 4. Launch in background
echo "🚀 Starting llama-server on 127.0.0.1:$PORT (4 threads, GBNF grammar)..."
nohup llama-server \
    -m "$MODEL_FILE" \
    --host 127.0.0.1 \
    --port "$PORT" \
    -c 2048 \
    -t 4 \
    --grammar-file "$GRAMMAR_FILE" > "$LOG_FILE" 2>&1 &

PID=$!
echo "Process launched with PID: $PID"

# 5. Wait for readiness
for i in $(seq 1 10); do
    sleep 1
    if curl -s "http://127.0.0.1:$PORT/health" 2>/dev/null; then
        echo "✅ Offline AI server is READY and bound to http://127.0.0.1:$PORT"
        if command -v cmd >/dev/null 2>&1; then
            cmd notification post -S bigtext -t "Autonomous AI" "Agent Tag" "Local Offline Model Active (SmolLM2-1.7B)" >/dev/null 2>&1 || true
        fi
        exit 0
    fi
    echo -n "."
done

echo ""
echo "ℹ️ Server started. Check logs at: $LOG_FILE"
