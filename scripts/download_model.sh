#!/bin/bash
# Download GGUF models for Pithon (Raspberry Pi 4/5 and CI)
# Usage: ./scripts/download_model.sh [qwen|smollm|all] [destination_dir]
set -euo pipefail

CHOICE="${1:-qwen}"
DEST_DIR="${2:-models}"

QWEN_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
QWEN_FILE="qwen2.5-0.5b-instruct-q4_k_m.gguf"

SMOLLM_URL="https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF/resolve/main/SmolLM2-135M-Instruct-Q4_K_M.gguf"
SMOLLM_FILE="SmolLM2-135M-Instruct-Q4_K_M.gguf"

mkdir -p "$DEST_DIR"

download_one() {
    local url="$1"
    local name="$2"
    local target="$DEST_DIR/$name"

    if [ -f "$target" ] && [ $(stat -f%z "$target" 2>/dev/null || stat -c%s "$target" 2>/dev/null || echo 0) -gt 10000000 ]; then
        echo "==> Model already exists: $target"
        return 0
    fi

    echo "==> Downloading $name..."
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail --progress-bar -o "$target" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$target" "$url"
    else
        echo "error: neither curl nor wget found." >&2
        exit 1
    fi
    echo "==> Successfully downloaded $target"
}

case "$CHOICE" in
    qwen)
        download_one "$QWEN_URL" "$QWEN_FILE"
        ;;
    smollm)
        download_one "$SMOLLM_URL" "$SMOLLM_FILE"
        ;;
    all)
        download_one "$SMOLLM_URL" "$SMOLLM_FILE"
        download_one "$QWEN_URL" "$QWEN_FILE"
        ;;
    *)
        echo "Usage: $0 [qwen|smollm|all] [destination_dir]" >&2
        exit 1
        ;;
esac
