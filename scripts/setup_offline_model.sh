#!/bin/bash
# Autonomous Android Controller — Offline Model Installer & Server
# Targets: Samsung Galaxy M56 (Exynos 1480, ARMv8.2-A asimddp)

set -e

MODEL_DIR="/sdcard/agent/models"
GRAMMAR_DIR="/sdcard/agent/grammars"
mkdir -p "$MODEL_DIR" "$GRAMMAR_DIR"

MODEL_FILE="$MODEL_DIR/smollm2-1.7b-instruct-q4_k_m.gguf"
MODEL_URL="https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/resolve/main/smollm2-1.7b-instruct-q4_k_m.gguf"

echo "=== [1/4] Checking Storage & Memory ==="
df -h "$MODEL_DIR"

echo "=== [2/4] Downloading SmolLM2-1.7B-Instruct (Q4_K_M) ==="
if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading 1.06 GB GGUF model..."
    curl -L -C - -o "$MODEL_FILE" "$MODEL_URL"
else
    echo "Model already present at: $MODEL_FILE"
fi

echo "=== [3/4] Ensuring Termux Dependencies ==="
if command -v pkg >/dev/null 2>&1; then
    pkg update -y && pkg install -y clang cmake git libomp
fi

echo "=== [4/4] Starting Local llama-server on 127.0.0.1:8080 ==="
echo "Binding to localhost with 4 performance threads and GBNF grammar constraints..."

if command -v llama-server >/dev/null 2>&1; then
    llama-server         -m "$MODEL_FILE"         --host 127.0.0.1         --port 8080         -c 2048         -t 4         --grammar-file "$GRAMMAR_DIR/action.gbnf"
else
    echo "llama-server not found in PATH. Build with: cmake -B build && cmake --build build --config Release"
fi
