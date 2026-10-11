import pytest
import json
import threading
import urllib.request
import urllib.error
from pithon.server import is_loopback_authorized, make_server_handler
from http.server import HTTPServer

def test_is_loopback_authorized_valid():
    port = 8080
    assert is_loopback_authorized("127.0.0.1:8080", "", port) is True
    assert is_loopback_authorized("localhost:8080", "", port) is True
    assert is_loopback_authorized("127.0.0.1:8080", "http://127.0.0.1:8080", port) is True
    assert is_loopback_authorized("localhost:8080", "http://localhost:8080", port) is True

def test_is_loopback_authorized_cross_origin_blocked():
    port = 8080
    # Evil origin from browser
    assert is_loopback_authorized("127.0.0.1:8080", "http://evil.example.com", port) is False
    assert is_loopback_authorized("127.0.0.1:8080", "https://malicious.site", port) is False
    # Different port
    assert is_loopback_authorized("127.0.0.1:8080", "http://127.0.0.1:9090", port) is False

def test_is_loopback_authorized_external_host_blocked():
    port = 8080
    assert is_loopback_authorized("192.168.1.50:8080", "", port) is False
    assert is_loopback_authorized("example.com:8080", "", port) is False

class MockEngine:
    model_type = "qwen"
    def generate_stream(self, prompt, temperature=0.0, max_tokens=512):
        yield "Hello "
        yield "world!"

def test_server_health_and_api():
    engine = MockEngine()
    handler_cls = make_server_handler(engine, port=18080)
    server = HTTPServer(("127.0.0.1", 18080), handler_cls)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        # 1. Health check
        req = urllib.request.Request("http://127.0.0.1:18080/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"

        # 2. Blocked external origin
        bad_req = urllib.request.Request(
            "http://127.0.0.1:18080/v1/chat/completions",
            headers={"Origin": "http://evil.com", "Content-Type": "application/json"},
            data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(bad_req, timeout=5)
        assert exc_info.value.code == 403

        # 3. Valid completions call
        valid_req = urllib.request.Request(
            "http://127.0.0.1:18080/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
        )
        with urllib.request.urlopen(valid_req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert "choices" in data
            assert data["choices"][0]["message"]["content"] == "Hello world!"
    finally:
        server.shutdown()
        server.server_close()
