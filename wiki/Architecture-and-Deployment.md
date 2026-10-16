# Architecture & Edge Deployment Guide

Khepri is engineered from the ground up for strict resource budgeting on ARM edge devices (Raspberry Pi 4/5) and low-resource cloud VPS instances (e.g., Oracle Cloud 2-core ARM Ampere A1, Hetzner, AWS Graviton).

---

## 1. Dual Microservice Architecture

```
                    +---------------------------------------------------+
                    |                 Host Server / OS                  |
                    | (Nginx Reverse Proxy / Let's Encrypt SSL / Ports) |
                    +-------------------------+-------------------------+
                                              |
                   Loopback :8091             |       Loopback :8090
                         |                    |             |
           +-------------v-------------+      |      +------v--------------------+
           |       Khepri Agent        |      |      |       Khepri Daemon       |
           |    (Python Microservice)  |      |      |     (C++ llama.cpp)       |
           |                           |      |      |                           |
           | - Telegram Bot Polling    |      |      | - Qwen2.5-0.5B GGUF Model |
           | - Fast-Path Router (<3ms) |      |      | - In-Memory mmap Tensor   |
           | - Edge OCR & Image Tools  |      |      | - OpenAI-compatible API   |
           | - Background Schedulers   +----->+----->+ - Strict Host Whitelist   |
           | - Hybrid Markdown Stores  | HTTP Loopback | - 2 Threads / Batch 128 |
           | - Frosted Glass Web UI    |  JSON API   |                           |
           +---------------------------+             +---------------------------+
```

---

## 2. Deployment Options

Khepri runs as **two processes** under both supported paths: the SLM daemon, and the agent (Telegram bot +
scheduler + web portal). The agent never loads the model — it reaches the daemon over loopback HTTP.

### Option A — Docker Compose (recommended default)

| Container | Role | Host Binding |
| :--- | :--- | :--- |
| `pithon` | llama.cpp SLM daemon | `127.0.0.1:8090` |
| `pithon-agent` | Telegram bot + scheduler + web portal | `127.0.0.1:8091` |

```bash
cp .env.example .env && nano .env    # TELEGRAM_BOT_TOKEN, WEB_ADMIN_PASSWORD, TIMEZONE
docker compose up -d --build
```

The daemon downloads the default Qwen2.5-0.5B GGUF (~350 MB) on first start.

### Option B — Bare metal + systemd

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e .[dev]
./scripts/download_model.sh qwen models
```

Because the daemon and agent are separate processes, Khepri ships **two** units:

```bash
# Edit User= and the /home/<you>/code/Khepri paths in BOTH units first.
chmod 600 .env                        # the agent loads .env relative to WorkingDirectory
sudo cp scripts/pithon-daemon.service scripts/pithon-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pithon-daemon.service
sudo systemctl enable --now pithon-agent.service
```

> **Port caveat:** the shipped units serve the daemon on **8090** (matching Compose and
> `scripts/query_daemon.sh`), not the `khepri serve` default of 8080. The agent unit sets
> `PITHON_DAEMON_URL=http://127.0.0.1:8090` to match — change both together if you prefer 8080.

`scripts/pithon.service` is a superseded single unit kept for reference only; do not enable it.

### Verifying Any Deployment

```bash
curl http://127.0.0.1:8090/health     # daemon: {"status":"ok","model":...}
curl http://127.0.0.1:8091/           # web portal (login required)
./scripts/query_daemon.sh "hello"     # streamed completion straight from the daemon
```

---

## 3. 4GB Raspberry Pi 4/5 Edge Memory Budget

When co-located alongside mission-critical services like **OwnTracks Recorder**, **Mosquitto MQTT**, or system databases, Khepri enforces hard Linux cgroup constraints:

| Service / Component | CPU Limit | RAM Hard Limit | Typical Live RSS | Volume Mounts |
| :--- | :--- | :--- | :--- | :--- |
| **`pithon-daemon`** | `1.0 CPU` (1 core) | `1408 MB` | ~306 MB | `./models:/app/models` |
| **`pithon-agent`** | `0.5 CPU` (half core) | `512 MB` | ~27 MB | `./data:/app/data` |
| **Combined Containers** | `1.5 CPU` | `1920 MB` | **~333 MB** (<8% of 4GB Pi 4) | Shared network |

### Why This Architecture Excels on a 4GB Pi 4:
1. **Host Memory Guarantee:** The combined cgroup ceiling is 1920 MiB — under the project's stated **< 2 GB total runtime budget** — while combined container RSS is only ~333 MiB, leaving >3.1 GB of RAM free for the host OS, desktop GUI, or companion Docker containers.
2. **Zero Swap Thrashing:** Qwen2.5-0.5B runs fully memory-mapped in RAM, eliminating MicroSD read/write bottlenecks.
3. **C++ Tesseract OCR vs Heavy ONNX/OpenCV:** Standard ONNX runtime and OpenCV model loading peaks over 500MB and causes OOM kills under tight cgroup limits. Khepri utilizes system C++ `tesseract-ocr` (~25MB package, ~20MB RAM) for instantaneous, crash-free OCR.
4. **Deterministic Fast-Path Bypass:** High-frequency queries (Time, Agenda, Weather, AST Math) execute in <3ms without waking the LLM inference threads.
5. **Loopback Protection:** Neither container exposes ports to public `0.0.0.0`; both strictly bind to `127.0.0.1` on the host.

---

## 4. Hybrid Markdown Memory Filesystem Layout

```
data/
├── profile.md               # User persona, communication style, frontmatter metadata
├── tasks.md                 # Standard GitHub-flavored checklist (- [ ] task)
├── notes/                   # Persistent Markdown knowledge notes vault
│   ├── daily_summary_*.md   # 5:00 AM nightly conversational summaries
│   └── architecture_*.md    # User notes & whiteboard transcriptions
├── briefings/               # Archived daily morning and evening briefings
│   └── 2026-10-*.md
└── pithon.db                # SQLite: 1-min calendar alert cache & web sessions
```

All markdown stores implement thread-level locking and atomic filesystem writes using `os.replace` to guarantee data integrity across concurrent Telegram and Web UI operations.

---

## 5. Automated Lifecycle Schedulers

* **05:00 AM — Memory Compactor:** Consolidates daily conversation turns into `data/notes/daily_summary_YYYY-MM-DD.md`.
* **09:00 AM — Daily Briefing:** Weather, news headlines, historical milestones, quote, agenda, and pending tasks.
* **07:30 PM (19:30) — Evening Wrap-Up:** Task completion recap and preview of tomorrow's meetings.
* **1-Minute Alert Tick:** Scans upcoming calendar events within the alert threshold.
* **5-Minute Calendar Sync:** Synchronizes with open ICS calendar feeds.

---

## 6. Supported Model Weights

| Model | Parameters | Quantization | Size on Disk | Typical Inference RAM | Speed on Cortex-A72 (Pi 4) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen2.5-0.5B-Instruct** *(Default)* | 0.49B | `Q4_K_M` | 352 MB | ~306 MB | 10-14 tokens/sec |
| **SmolLM2-135M-Instruct** | 0.13B | `Q4_K_M` | 98 MB | ~180 MB | 24-32 tokens/sec |
| **SmolLM2-360M-Instruct** | 0.36B | `Q4_K_M` | 245 MB | ~280 MB | 16-20 tokens/sec |

Download script helper:
```bash
# Download default Qwen2.5-0.5B
./scripts/download_model.sh qwen models

# Download SmolLM2-135M
./scripts/download_model.sh smollm models
```
