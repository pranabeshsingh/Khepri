"""Loopback OpenAI-compatible daemon with Host and Origin validation."""

import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Type
from pithon.template import format_chat_prompt

ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "pithon", "pithon-daemon"}

def is_loopback_authorized(host: str, origin: str, port: int = 8080) -> bool:
    """Verify that the request is strictly loopback and Origin is legitimate."""
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"pithon:{port}", f"pithon-daemon:{port}"}
    clean_host = host.lower().strip()
    host_name = clean_host.split(":")[0]
    if host_name not in ALLOWED_HOSTNAMES:
        return False

    clean_origin = origin.lower().strip()
    if clean_origin:
        if clean_origin.startswith("http://"):
            origin_netloc = clean_origin[len("http://"):].rstrip("/").split("/")[0]
            if origin_netloc != clean_host and origin_netloc not in allowed:
                return False
        else:
            return False

    return True

def make_server_handler(engine: Any, port: int) -> Type[BaseHTTPRequestHandler]:
    """Create a request handler bound to the given engine instance and port."""
    start_time = time.time()

    class PithonHandler(BaseHTTPRequestHandler):
        def _check_security(self) -> bool:
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin", "")
            if not is_loopback_authorized(host, origin, port):
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Forbidden: Loopback access only"}')
                return False
            return True

        def do_GET(self) -> None:
            if not self._check_security():
                return

            if self.path == "/health":
                uptime = int(time.time() - start_time)
                payload = {
                    "status": "ok",
                    "uptime_sec": uptime,
                    "model": getattr(engine, "model_path", "unknown"),
                    "threads": getattr(engine, "n_threads", 1),
                }
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/v1/models":
                payload = {
                    "object": "list",
                    "data": [{
                        "id": getattr(engine, "model_path", "pithon-model"),
                        "object": "model",
                        "owned_by": "pithon"
                    }]
                }
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            if not self._check_security():
                return

            if self.path == "/v1/chat/completions":
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len == 0:
                    self.send_response(400)
                    self.end_headers()
                    return

                raw_body = self.rfile.read(content_len)
                try:
                    req_data = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error": "Invalid JSON body"}')
                    return

                messages = req_data.get("messages", [])
                stream = req_data.get("stream", False)
                temperature = float(req_data.get("temperature", 0.0))
                max_tokens = int(req_data.get("max_tokens", 512))

                model_type = getattr(engine, "model_type", "qwen")
                prompt = format_chat_prompt(messages, model_type=model_type)

                req_id = f"chatcmpl-{int(time.time() * 1000)}"
                created_ts = int(time.time())

                if stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()

                    for chunk in engine.generate_stream(prompt, temperature=temperature, max_tokens=max_tokens):
                        event = {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": getattr(engine, "model_path", "pithon"),
                            "choices": [{"delta": {"content": chunk}, "finish_reason": None}]
                        }
                        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
                        self.wfile.flush()

                    done_event = {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": getattr(engine, "model_path", "pithon"),
                        "choices": [{"delta": {}, "finish_reason": "stop"}]
                    }
                    self.wfile.write(f"data: {json.dumps(done_event)}\n\ndata: [DONE]\n\n".encode("utf-8"))
                    self.wfile.flush()
                else:
                    tokens = []
                    for chunk in engine.generate_stream(prompt, temperature=temperature, max_tokens=max_tokens):
                        tokens.append(chunk)
                    full_content = "".join(tokens)

                    resp_data = {
                        "id": req_id,
                        "object": "chat.completion",
                        "created": created_ts,
                        "model": getattr(engine, "model_path", "pithon"),
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": full_content},
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": len(prompt.split()),
                            "completion_tokens": len(tokens),
                            "total_tokens": len(prompt.split()) + len(tokens)
                        }
                    }
                    body = json.dumps(resp_data).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return PithonHandler

def run_server(engine: Any, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run loopback daemon on specified port."""
    handler_cls = make_server_handler(engine, port=port)
    server = HTTPServer((host, port), handler_cls)
    print(f"\n  Pithon daemon listening on http://{host}:{port} (loopback only)\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Pithon daemon...")
    finally:
        server.server_close()
