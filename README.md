# Pithon

**Ultra-lightweight Small Language Model runtime engineered for Raspberry Pi 3.**

Run a 0.5B instruction-tuned model locally in under **350 MB RAM** on a 1.2 GHz ARM Cortex-A53 CPU. Pithon is designed for resource-constrained edge devices to handle piped log analysis, simple weather formatting, and task reminder parsing with low memory overhead.

---

## Why Pithon on Raspberry Pi 3?

* **Strict Memory Budget (< 550 MB RSS)**: Runs comfortably within the Pi 3's 1 GB RAM, keeping 450+ MB free for Raspberry Pi OS to avoid MicroSD swap thrashing.
* **In-Memory GGUF**: Unlike MoE streaming across NVMe SSDs, a 0.5B model is fully memory-mapped in RAM, eliminating MicroSD read latency during token generation.
* **CPU Core Allocation**: Computes on 3 threads by default (`--threads 3`), reserving 1 core for SSH and background OS responsiveness.
* **Three Operational Modes**:
  1. **Log Piping (`pithon pipe`)**: Ingest logs from `stdin` (`journalctl`, `syslog`), auto-budget context, diagnose errors, and exit.
  2. **Interactive Chat (`pithon chat`)**: Multi-turn terminal REPL over SSH.
  3. **Loopback Daemon (`pithon serve`)**: OpenAI-compatible `/v1/chat/completions` API server with loopback security.

---

## Quickstart

### 1. Installation on Raspberry Pi

```bash
# Clone the repository
git clone https://github.com/pranabesh/Pithon.git
cd Pithon

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install llama-cpp-python with ARM NEON acceleration
pip install --upgrade pip
pip install llama-cpp-python
pip install -e .
```

### 2. Download the Model (~350 MB)

```bash
./scripts/download_model.sh
```
This fetches `qwen2.5-0.5b-instruct-q4_k_m.gguf` from Hugging Face into `./models/`.

---

## Usage

### 1. Piped Log Analysis

Analyze system logs or application output directly from the command line:

```bash
# Diagnose recent systemd service errors
journalctl -u nginx -n 50 | pithon pipe "What caused the failure?"

# Diagnose syslog using the log-analyzer preset
cat /var/log/syslog | pithon pipe --preset log-analyzer
```

**Built-in Task Presets:**
* `--preset log-analyzer`: Focuses on error codes, timestamps, and root causes in 3 concise bullet points.
* `--preset reminder`: Parses natural language tasks into structured JSON (`{"task": ..., "time": ...}`).
* `--preset weather`: Summarizes weather observation data into 2 actionable sentences.

### 2. Interactive Terminal Chat

Start an interactive chat session inside your SSH terminal:

```bash
pithon chat
```

Special commands inside the chat:
* `/clear` — Reset conversation history
* `/exit` or `/quit` — Exit chat session

### 3. Background OpenAI API Server

Start a background server on `127.0.0.1:8080`:

```bash
pithon serve --port 8080
```

You can now query it using `curl` or any OpenAI-compatible client:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is 25 Celsius in Fahrenheit?"}],
    "stream": false
  }'
```

Check system status and memory:
```bash
curl http://127.0.0.1:8080/health
```

---

## Running as a systemd Service on the Pi

To have Pithon run automatically on boot:

```bash
sudo cp scripts/pithon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pithon
```

Check service status:
```bash
systemctl status pithon
```

---

## Development & Testing

Run the test suite:
```bash
.venv/bin/pytest tests/ -v
```

Pithon includes a mock mode (`--mock`) allowing all commands and servers to be tested without downloading model weights:
```bash
echo "Test log" | pithon pipe --mock
pithon chat --mock
pithon serve --mock
```

---

## License

Apache-2.0
