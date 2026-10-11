"""End-to-End tests exercising live inference on native ARM64 / host runners."""

import json
import os
import resource
import sys
import threading
import time
import urllib.request
from io import StringIO
import pytest

from pithon.engine import LlamaEngine
from pithon.pipe import run_pipe
from pithon.server import make_server_handler
from http.server import HTTPServer

def get_available_test_model():
    """Find any downloaded GGUF model in models/."""
    candidates = [
        "models/smollm-135m-instruct-q4_k_m.gguf",
        "models/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    ]
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 10 * 1024 * 1024:
            return path
    return None

TEST_MODEL_PATH = get_available_test_model()

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        TEST_MODEL_PATH is None,
        reason="No real GGUF model found in models/. Run ./scripts/download_model.sh to fetch."
    )
]

@pytest.fixture(scope="module")
def live_engine():
    """Module-scoped live engine to avoid reloading weights repeatedly."""
    print(f"\n[E2E] Loading live model: {TEST_MODEL_PATH}")
    engine = LlamaEngine(model_path=TEST_MODEL_PATH, n_ctx=1024, n_threads=3)
    return engine

def test_e2e_pipe_real_inference(live_engine):
    """Test pithon pipe with real kernel logs."""
    sample_log = (
        "Oct 11 12:00:01 rpi kernel: [12345.67] Out of memory: Kill process 1024 (mysqld) score 850 or sacrifice child\n"
        "Oct 11 12:00:01 rpi kernel: [12345.68] Killed process 1024 (mysqld) total-vm:850000kB, anon-rss:520000kB\n"
    )
    out = StringIO()
    exit_code = run_pipe(
        engine=live_engine,
        user_prompt="Explain what crashed and why in two sentences.",
        preset="log-analyzer",
        stdin_content=sample_log,
        out_stream=out
    )
    result = out.getvalue().strip()
    print(f"\n[E2E Pipe Output]:\n{result}")

    assert exit_code == 0
    assert len(result) > 10
    # The model should generate a recognizable diagnosis
    lower = result.lower()
    assert any(w in lower for w in ["memory", "mysqld", "killed", "oom", "process"])

def test_e2e_server_live_streaming(live_engine):
    """Test live loopback daemon with Server-Sent Events streaming."""
    port = 19090
    handler_cls = make_server_handler(live_engine, port=port)
    server = HTTPServer(("127.0.0.1", port), handler_cls)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        # 1. Check health
        health_req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(health_req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"
            assert data["threads"] == live_engine.n_threads

        # 2. Check streaming completions
        payload = {
            "messages": [
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "What is 2 + 2? Answer with only the number."}
            ],
            "stream": True,
            "temperature": 0.0,
            "max_tokens": 16
        }
        stream_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload).encode()
        )

        chunks_received = []
        saw_done = False
        with urllib.request.urlopen(stream_req, timeout=30) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                if line_str == "data: [DONE]":
                    saw_done = True
                    break
                if line_str.startswith("data: "):
                    event_data = json.loads(line_str[6:])
                    delta = event_data["choices"][0]["delta"].get("content", "")
                    if delta:
                        chunks_received.append(delta)

        assert saw_done is True
        full_text = "".join(chunks_received).strip()
        print(f"\n[E2E Stream Output]: {full_text}")
        assert len(full_text) > 0
        assert "4" in full_text

        # 3. Check non-streaming completions
        payload["stream"] = False
        batch_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload).encode()
        )
        with urllib.request.urlopen(batch_req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            assert "choices" in data
            content = data["choices"][0]["message"]["content"]
            assert len(content) > 0
            assert "4" in content
    finally:
        server.shutdown()
        server.server_close()

def test_e2e_memory_footprint(live_engine):
    """Verify that resident set size remains within Pi 3 headroom limits (< 550 MB)."""
    # Force generating a block of tokens
    prompt = "<|im_start|>user\nWrite a list of numbers from 1 to 20.<|im_end|>\n<|im_start|>assistant\n"
    tokens = list(live_engine.generate_stream(prompt, max_tokens=100))
    assert len(tokens) > 0

    # Read resident memory
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS ru_maxrss is in bytes, Linux ru_maxrss is in kilobytes
    if sys.platform == "darwin":
        max_rss_mb = usage.ru_maxrss / (1024 * 1024)
    else:
        max_rss_mb = usage.ru_maxrss / 1024

    print(f"\n[E2E Peak RSS Memory]: {max_rss_mb:.2f} MB")
    # Verify ceiling strictly under 550 MB
    assert max_rss_mb < 550.0, f"Memory exceeded 550 MB ceiling: {max_rss_mb:.2f} MB"
