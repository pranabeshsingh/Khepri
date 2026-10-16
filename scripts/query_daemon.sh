#!/bin/bash
# Query the running Pithon daemon on 127.0.0.1:8090
# Usage:
#   ./scripts/query_daemon.sh "Explain this"
#   echo "kernel log" | ./scripts/query_daemon.sh "What crashed?"
set -euo pipefail

PROMPT="${1:-}"
PORT="${PITHON_PORT:-8090}"
URL="http://127.0.0.1:${PORT}/v1/chat/completions"

# Read piped stdin only when it is actually something worth reading.
#   -t 0 would also suppress a hang, but it races: a slow producer can have no
#   bytes ready yet, so the check fails and the piped input is silently dropped.
#   Inspecting the descriptor type instead is not racy -- a pipe or a redirected
#   file is read in full (blocking until the writer closes), while a TTY, a
#   closed stdin, or </dev/null is skipped without ever blocking.
STDIN_DATA=""
if [ ! -t 0 ] && { [ -p /dev/stdin ] || [ -f /dev/stdin ]; }; then
    STDIN_DATA=$(cat)
fi

FULL_CONTENT=""
if [ -n "$STDIN_DATA" ] && [ -n "$PROMPT" ]; then
    FULL_CONTENT="Context:
${STDIN_DATA}

Task: ${PROMPT}"
elif [ -n "$STDIN_DATA" ]; then
    FULL_CONTENT="${STDIN_DATA}"
else
    FULL_CONTENT="${PROMPT}"
fi

if [ -z "$FULL_CONTENT" ]; then
    echo "Usage: $0 \"Your prompt\" or echo \"logs\" | $0 [prompt]" >&2
    exit 1
fi

PAYLOAD=$(python3 -c '
import json, sys
content = sys.argv[1]
data = {
    "messages": [{"role": "user", "content": content}],
    "stream": True,
    "temperature": 0.0,
    "max_tokens": 512
}
print(json.dumps(data))
' "$FULL_CONTENT")

curl -s -N -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | while read -r line; do
    if [ "$line" = "data: [DONE]" ]; then
        break
    fi
    if [[ "$line" =~ ^data:\ (.*) ]]; then
        python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
    delta = d["choices"][0]["delta"].get("content", "")
    sys.stdout.write(delta)
    sys.stdout.flush()
except Exception:
    pass
' "${BASH_REMATCH[1]}"
    fi
done
echo ""
