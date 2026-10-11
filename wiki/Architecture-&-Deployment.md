# Architecture & Edge Deployment Guide

Khepri is engineered from the ground up for strict resource budgeting on ARM edge devices (Raspberry Pi 3/4/5) and low-resource cloud VPS instances (e.g., Oracle Cloud 2-core ARM Ampere A1, Hetzner, AWS Graviton).

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
           | - Tool Interceptors       |      |      | - In-Memory mmap Tensor   |
           | - Background Cron Task    +----->+----->+ - OpenAI-compatible API   |
           | - SQLite DB (/app/data)   | HTTP Loopback | - Strict Host Whitelist |
           | - Markdown Notes (/notes) |  JSON API   | - 2 Threads / Batch 128   |
           | - Frosted Glass Web UI    |             +---------------------------+
           +---------------------------+
```

---

## 2. Resource Budgets & Cgroup Limits

When co-located alongside mission-critical services like **OwnTracks Recorder**, **Mosquitto MQTT**, or system databases, Khepri enforces hard Linux cgroup constraints:

| Container | CPU Limit | RAM Hard Limit | Typical RSS | Volume Mounts |
| :--- | :--- | :--- | :--- | :--- |
| **`pithon-daemon`** | `1.0 CPU` (1 core) | `2048 MB` | ~780 MB | `./models:/app/models` |
| **`pithon-agent`** | `0.5 CPU` (half core) | `512 MB` | ~90 MB | `./data:/app/data` |

### Why This Matters:
1. **Host CPU Guarantee:** The host OS and background services always have guaranteed compute headroom.
2. **Zero Swap Thrashing:** Qwen2.5-0.5B runs fully memory-mapped in RAM, eliminating MicroSD read bottlenecks on Raspberry Pi.
3. **Loopback Protection:** Neither container exposes ports to public 0.0.0.0; both strictly bind to `127.0.0.1` on the host.

---

## 3. Supported Model Weights

Khepri supports any standard GGUF instruction-tuned model. Recommended options:

| Model | Parameters | Quantization | Size on Disk | Typical Inference RAM | Speed on Cortex-A53 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen2.5-0.5B-Instruct** *(Default)* | 0.49B | `Q4_K_M` | 352 MB | ~480 MB | 8-12 tokens/sec |
| **SmolLM2-135M-Instruct** | 0.13B | `Q4_K_M` | 98 MB | ~180 MB | 24-32 tokens/sec |
| **SmolLM2-360M-Instruct** | 0.36B | `Q4_K_M` | 245 MB | ~390 MB | 14-18 tokens/sec |

Download script helper:
```bash
# Download default Qwen2.5-0.5B
./scripts/download_model.sh qwen models

# Download SmolLM2-135M
./scripts/download_model.sh smollm models
```
