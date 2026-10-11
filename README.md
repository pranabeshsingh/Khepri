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

---

## Docker Deployment (Resource-Constrained Multi-Service Hosts)

When running Pithon alongside critical background services (e.g. OwnTracks, MQTT brokers, databases) on low-resource ARM or x86 VPS instances (like Oracle Cloud 2-core ARM), Pithon can be deployed using Docker with strict cgroup isolation to guarantee zero CPU or RAM starvation for other workloads.

### 1. Launch with Docker Compose
```bash
docker compose up -d --build
```

### 2. Resource Limits & Port Isolation
* **CPU Limit (`cpus: 1.0`)**: Caps Pithon to at most 1 CPU core, guaranteeing the host and co-located services always have dedicated CPU headroom.
* **Memory Limit (`mem_limit: 2048m`)**: Strict 2 GB hard limit. Pithon with Qwen2.5-0.5B runs at ~780 MB RSS, leaving massive headroom while protecting the host.
* **Network Binding (`127.0.0.1:8090:8080`)**: Binds exclusively to host loopback port 8090. Not exposed to the public internet, avoiding port collisions.

### 3. Query the Running Daemon
Query directly via curl or the helper script:
```bash
# Direct curl
curl -s http://127.0.0.1:8090/health

# Stream log diagnostics into the daemon
dmesg | ./scripts/query_daemon.sh "Identify hardware errors"
```

## License

Apache-2.0
