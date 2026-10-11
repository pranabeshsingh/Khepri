# Pithon (`pithon`) Design Specification

**Date:** 2026-10-11  
**Target Hardware:** Raspberry Pi 3 (ARM Cortex-A53 @ 1.2 GHz, 1 GB LPDDR2 RAM)  
**Target OS:** Raspberry Pi OS 64-bit (`aarch64`) or 32-bit (`armv7l`)  
**Language/Runtime:** Python 3.12 (native virtual environment)  
**Target Workloads:** Piped log diagnostics, simple weather formatting, structured task reminders  

---

## 1. System Goals & Hardware Constraints

### 1.1 Hardware Budget
* **CPU:** Quad-core ARM Cortex-A53 (1.2 GHz).
* **RAM:** 1,024 MB physical memory.
* **Storage:** MicroSD card (sequential read ~20–40 MB/s, random 4K read ~1–5 MB/s).
* **Memory Ceiling:** Total resident memory (Python process + model weights + KV cache + working heap) must strictly remain **under 550 MB RSS** to guarantee at least 450 MB for the Linux kernel and prevent OS swap thrashing on the MicroSD card.
* **Compute Allocation:** Defaults to **3 worker threads** (`--threads 3`), keeping 1 CPU core free for SSH sessions and background OS responsiveness.

### 1.2 Model Selection
* **Architecture:** Sub-1B dense Small Language Model (SLM) in GGUF format:
  * Primary: **Qwen2.5-0.5B-Instruct** (`Q4_K_M` ~350 MB or `Q3_K_M` ~280 MB).
  * Alternative: **SmolLM-360M-Instruct** (`Q4_K_M` ~220 MB).
* **Quantization:** 4-bit integer quantization with ARM NEON SIMD acceleration.
* **In-Memory Residency:** The 0.5B model is fully memory-mapped into physical RAM on startup, completely avoiding MicroSD read latency during token generation.

---

## 2. Architecture & Package Structure

The project is structured as a clean, modular Python package with zero bloated framework dependencies:

```text
Pithon/
├── pyproject.toml              # Build metadata & entrypoint `pithon = "pithon.cli:main"`
├── requirements.txt            # Runtime dependencies (llama-cpp-python)
├── requirements-dev.txt        # Development/testing dependencies (pytest)
├── pithon/
│   ├── __init__.py             # Package version & public API
│   ├── engine.py               # llama-cpp-python wrapper, memory checks, sampling
│   ├── template.py             # Chat templates (Qwen2.5 / SmolLM turn formatting)
│   ├── presets.py              # System prompt presets (log-analyzer, reminder, weather)
│   ├── pipe.py                 # Piped stdin processor & log budgeting
│   ├── chat.py                 # Interactive terminal chat loop
│   ├── server.py               # Standard-library loopback HTTP server (OpenAI /v1 API)
│   └── cli.py                  # Argument parser dispatching to pipe, chat, serve
├── tests/
│   ├── test_template.py        # Chat formatting tests
│   ├── test_presets.py         # Prompt presets tests
│   ├── test_pipe.py            # Log truncation & budgeting tests
│   └── test_server_security.py # Loopback Host & Origin validation tests
└── scripts/
    ├── download_model.sh       # Fetch target GGUF checkpoint
    └── pithon.service          # Systemd unit file for headless Pi deployment
```

---

## 3. Core Components & Interfaces

### 3.1 Interface Modes

#### A. Log Piping Mode (`pithon pipe`)
* **Purpose:** Process piped system logs or terminal output without opening an interactive session.
* **Syntax:**
  ```bash
  journalctl -u nginx -n 50 | pithon pipe "Check for errors or anomalies"
  cat /var/log/syslog | pithon pipe --preset log-analyzer
  ```
* **Log Budgeting & Chunking:**
  * Maximum context window is capped at 2,048 tokens.
  * If input exceeds 1,792 tokens, an intelligent truncation strategy retains the initial log header and the trailing 80% (where recent crashes occur), discarding repetitive middle lines.
* **Exit Behavior:** Streams results to `stdout`, flushes, and immediately terminates to release memory.

#### B. Interactive Terminal Chat (`pithon chat`)
* **Purpose:** Ad-hoc questions, reminders, and interactive testing in an SSH session.
* **Syntax:**
  ```bash
  pithon chat --model ./models/qwen2.5-0.5b-instruct-q4_k_m.gguf
  ```
* **Features:**
  * Interactive multi-turn chat history.
  * Word-by-word streaming token output.
  * Clean `SIGINT` (Ctrl+C) handling.

#### C. HTTP Daemon Mode (`pithon serve`)
* **Purpose:** Headless background service (can run under `systemd`).
* **Syntax:**
  ```bash
  pithon serve --port 8080 --model ./models/qwen2.5-0.5b-instruct-q4_k_m.gguf
  ```
* **Endpoints:**
  * `POST /v1/chat/completions`: Standard OpenAI-compatible schema supporting streaming (`stream: true`) and non-streaming responses.
  * `GET /health`: JSON status reporting model load state, uptime, and resident memory usage.
* **Security & Sandboxing:**
  * Built using Python's standard `http.server` (zero extra dependencies).
  * Binds exclusively to `127.0.0.1`.
  * Verifies `Host` and `Origin` headers to prevent DNS rebinding attacks and cross-origin browser access (Coachwhip pattern).

### 3.2 Task Presets & System Prompt Profiles
* **`log-analyzer`**: Identifies errors, warning codes, timestamps, and probable root causes in 3 bullet points.
* **`reminder`**: Extracts task name, date/time, and recurrence from user prompt into valid JSON: `{"task": string, "time": string, "due_today": boolean}`.
* **`weather`**: Summarizes raw forecast data into concise 2-sentence recommendations.

---

## 4. Execution Pipeline & Error Handling

* **Sampling Strategy:** Greedy sampling (`temperature: 0.0`) by default for log analysis; low-entropy sampling (`temperature: 0.2`, `top_p: 0.8`) for conversational chat and weather.
* **OOM Guard:** Reads `/proc/meminfo` (on Linux) before allocating fresh context. If available RAM is below 100 MB, requests return a clean error rather than triggering a kernel kill.
* **Signal Handling:** Graceful cleanup on `SIGINT` and `SIGTERM`.
