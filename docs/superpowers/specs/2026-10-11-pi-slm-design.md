# Raspberry Pi 3 SLM Engine (`pi-slm`) Design Specification

**Date:** 2026-10-11  
**Target Hardware:** Raspberry Pi 3 (ARM Cortex-A53 @ 1.2 GHz, 1 GB LPDDR2 RAM)  
**Target OS:** Raspberry Pi OS 64-bit (`aarch64`) or 32-bit (`armv7l`)  
**Target Workloads:** Piped log diagnostics, simple weather formatting, structured task reminders  

---

## 1. System Goals & Hardware Constraints

### 1.1 Hardware Budget
* **CPU:** Quad-core ARM Cortex-A53 (1.2 GHz).
* **RAM:** 1,024 MB physical memory.
* **Storage:** MicroSD card (sequential read ~20–40 MB/s, random 4K read ~1–5 MB/s).
* **Memory Ceiling:** The entire process (binary + model weights + KV cache + working heap) must strictly remain **under 550 MB RSS** to guarantee at least 450 MB for the Linux kernel, system daemons, and to prevent OS disk swapping to the slow MicroSD card.
* **Compute Allocation:** The inference engine defaults to **3 worker threads**, keeping 1 CPU core free for SSH sessions and background OS responsiveness.

### 1.2 Model Selection
* **Architecture:** Sub-1B dense Small Language Model (SLM) in GGUF format:
  * Primary: **Qwen2.5-0.5B-Instruct** (`Q4_K_M` ~350 MB or `Q3_K_M` ~280 MB).
  * Alternative: **SmolLM-360M-Instruct** (`Q4_K_M` ~220 MB).
* **Quantization:** 4-bit integer quantization with ARM NEON SIMD acceleration.
* **In-Memory Residency:** Unlike large MoE streaming on NVMe SSDs, a 0.5B model is fully memory-mapped into physical RAM on startup, completely bypassing MicroSD read latency during token generation.

---

## 2. Architecture & Crate Organization

The project is structured as a Rust workspace with clear separation of engine logic, server endpoints, and CLI interface:

```text
pi-slm/
├── Cargo.toml                  # Workspace definition
├── crates/
│   ├── engine/                 # Model loading, llama.cpp bindings, KV cache, tokenizer
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── model.rs        # Context initialization, token sampling, generation loop
│   │       └── template.rs     # Chat templates (Qwen/SmolLM chat formatting)
│   ├── server/                 # Lightweight HTTP server (OpenAI-compatible /v1 endpoints)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       └── api.rs          # /v1/chat/completions, /health, loopback verification
│   └── cli/                    # Unified executable (`pi-slm`)
│       ├── Cargo.toml
│       └── src/
│           ├── main.rs         # Subcommands: `pipe`, `chat`, `serve`
│           └── presets.rs      # System prompt presets (log-analyzer, reminder, weather)
└── scripts/
    ├── download_model.sh       # Fetch target GGUF checkpoint
    └── build_pi.sh             # Cross-compilation helper via `cross`
```

---

## 3. Core Components & Interfaces

### 3.1 Interface Modes

#### A. Log Piping Mode (`pi-slm pipe`)
* **Purpose:** Process piped system logs or terminal output without opening an interactive session.
* **Syntax:**
  ```bash
  journalctl -u nginx -n 50 | pi-slm pipe "Check for errors or anomalies"
  cat /var/log/syslog | pi-slm pipe --preset log-analyzer
  ```
* **Log Budgeting & Chunking:**
  * Maximum context window is capped at 2,048 tokens.
  * If input exceeds 1,792 tokens (leaving 256 tokens for output), an intelligent truncation strategy retains the initial log header and the trailing 80% (where the crash/error occurs), discarding intermediate repetitive logs.
* **Exit Behavior:** Streams results to `stdout`, flushes, and immediately terminates to release memory.

#### B. Interactive Terminal Chat (`pi-slm chat`)
* **Purpose:** Ad-hoc questions, reminders, and interactive testing in an SSH session.
* **Syntax:**
  ```bash
  pi-slm chat --model ./models/qwen2.5-0.5b-instruct-q4_k_m.gguf
  ```
* **Features:**
  * Interactive multi-turn chat history.
  * Word-by-word streaming token output.
  * Ctrl+C / SIGINT clean terminal restoration.

#### C. HTTP Daemon Mode (`pi-slm serve`)
* **Purpose:** Headless background service (can run under `systemd`).
* **Syntax:**
  ```bash
  pi-slm serve --port 8080 --model ./models/qwen2.5-0.5b-instruct-q4_k_m.gguf
  ```
* **Endpoints:**
  * `POST /v1/chat/completions`: Standard OpenAI-compatible schema supporting streaming (`stream: true`) and non-streaming responses.
  * `GET /health`: JSON status reporting model load state, uptime, and resident memory usage.
* **Security & Sandboxing:**
  * Binds exclusively to `127.0.0.1`.
  * Verifies `Host` and `Origin` headers to prevent DNS rebinding attacks and cross-origin browser requests (following the Coachwhip security pattern).

### 3.2 Task Presets & System Prompt Profiles
To ensure consistent quality from a 0.5B model without hallucinations, built-in task presets constrain the generation:
* **`log-analyzer`**:
  * System prompt: `"You are a concise system administrator assistant. Analyze the provided log lines. Identify errors, warning codes, timestamps, and suggest the most probable root cause in 3 concise bullet points. Avoid filler text."`
* **`reminder`**:
  * System prompt: `"You are a task reminder parser. Extract task name, date/time, and recurrence from the user prompt into valid JSON: {\"task\": string, \"time\": string, \"due_today\": boolean}."`
* **`weather`**:
  * System prompt: `"You are a friendly weather assistant. Given raw forecast data, provide a 2-sentence summary with temperature, conditions, and clothing recommendations."`

---

## 4. Execution Pipeline & Resilience

### 4.1 Sampling Strategy
* **Greedy Sampling (`temperature: 0.0`)**: Default for `pipe` and log analysis to ensure deterministic, factual extraction.
* **Low-Entropy Sampling (`temperature: 0.2`, `top_p: 0.8`)**: Used for conversational chat and weather summaries.

### 4.2 Error Handling & Resource Protection
* **OOM Guard:** The engine queries `/proc/meminfo` before allocating fresh context. If available system RAM is below 100 MB, incoming inference requests are rejected with an explicit error rather than risking a kernel OOM kill.
* **Context Limit Guard:** Input exceeding 2,048 tokens is rejected or truncated cleanly with a diagnostic warning.
* **Graceful Termination:** Registers signal handlers for `SIGINT` and `SIGTERM` to safely release mapped files and model contexts.

---

## 5. Build & Deployment Plan

### 5.1 Cross-Compilation Workflow
Building `llama.cpp` on the Pi 3 directly is slow due to limited RAM and CPU speed. Compilation will be performed using `cross` on the development workstation:
```bash
# Target: 64-bit ARM Linux (Raspberry Pi OS 64-bit)
cross build --release --target aarch64-unknown-linux-gnu
```

### 5.2 Deployment Script (`scripts/build_pi.sh`)
* Generates a self-contained release archive containing:
  1. The compiled `pi-slm` static binary.
  2. Model download script.
  3. Sample `systemd` service unit file (`pi-slm.service`).
