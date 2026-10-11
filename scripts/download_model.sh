#!/bin/bash
# Download Qwen2.5-0.5B-Instruct GGUF (Q4_K_M, ~350 MB) for Raspberry Pi 3
set -euo pipefail

DEST_DIR="${1:-models}"
MODEL_FILE="qwen2.5-0.5b-instruct-q4_k_m.gguf"
URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"

mkdir -p "$DEST_DIR"
TARGET="$DEST_DIR/$MODEL_FILE"

if [ -f "$TARGET" ]; then
    echo "==> Model already exists at: $TARGET"
    exit 0
fi

echo "==> Downloading Qwen2.5-0.5B-Instruct (Q4_K_M ~350 MB)..."
if command -v curl >/dev/null 2>&1; then
    curl -L --progress-bar -o "$TARGET" "$URL"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$TARGET" "$URL"
else
    echo "error: neither curl nor wget found." >&2
    exit 1
fi

echo "==> Model successfully downloaded to $TARGET"
