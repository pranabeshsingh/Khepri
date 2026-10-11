#!/bin/bash
set -e

MODEL_PATH="${PITHON_MODEL:-/app/models/qwen2.5-0.5b-instruct-q4_k_m.gguf}"

# If running serve and model does not exist, download default qwen model automatically
if [ ! -f "$MODEL_PATH" ] && [ "$1" = "pithon" ]; then
    echo "==> Model not found at $MODEL_PATH."
    echo "==> Downloading default Qwen2.5-0.5B model (~350MB)..."
    /app/scripts/download_model.sh qwen /app/models
fi

exec "$@"
