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

## 2. 4GB Raspberry Pi 4 Edge Memory Budget

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

## 3. Hybrid Markdown Memory Filesystem Layout

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

## 4. Automated Lifecycle Schedulers

* **05:00 AM — Memory Compactor:** Consolidates daily conversation turns into `data/notes/daily_summary_YYYY-MM-DD.md`.
* **09:00 AM — Daily Briefing:** Weather, news headlines, historical milestones, quote, agenda, and pending tasks.
* **07:30 PM (19:30) — Evening Wrap-Up:** Task completion recap and preview of tomorrow's meetings.
* **1-Minute Alert Tick:** Scans upcoming calendar events within the alert threshold.
* **5-Minute Calendar Sync:** Synchronizes with open ICS calendar feeds.

---

## 5. Supported Model Weights

| Model | Parameters | Quantization | Size on Disk | Typical Inference RAM | Speed on Cortex-A72 |
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
