# Contributing to Khepri

Thank you for your interest in contributing to **Khepri**! Khepri is an open-source, lightweight SLM runtime and autonomous personal agent designed specifically for ARM64 and low-power edge hardware like Raspberry Pi 4/5.

We welcome contributions of all kinds: bug fixes, documentation improvements, new tool integrations, benchmark profiles, and accessibility enhancements.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to **pranz29@live.com**.

---

## Getting Started

1. **Check existing issues and discussions:** Before opening a new issue or PR, search our [Issues](https://github.com/pranabeshsingh/Khepri/issues) and [Discussions](https://github.com/pranabeshsingh/Khepri/discussions) to see if it has already been discussed.
2. **Propose larger features first:** For major architectural changes or new tools, please open a [Discussion](https://github.com/pranabeshsingh/Khepri/discussions) or an RFC issue first so we can align on design and memory implications.
3. **Fork and branch:** Fork the repository on GitHub, then create a feature branch off `master`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Local Development Setup

### Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- `git`
- (Optional) `tesseract-ocr` for image OCR tools:
  - macOS: `brew install tesseract`
  - Debian/Ubuntu/Raspberry Pi OS: `sudo apt install tesseract-ocr`

### Setup Instructions

```bash
# 1. Clone your fork
git clone https://github.com/<your-username>/Khepri.git
cd Khepri

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip tooling
pip install --upgrade pip

# 4. Install dependencies with pre-built CPU wheels for llama-cpp-python
pip install --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e .[dev]
```

> **Note on `llama-cpp-python`:** PyPI only provides source archives for `llama-cpp-python`. Specifying `--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu` allows `pip` to install official, optimized prebuilt wheels for your architecture (`linux_x86_64`, `manylinux2014_aarch64`, or `macosx_arm64`), saving 20+ minutes of local compilation.

---

## Codebase Architecture

- **`pithon/engine.py`**: Model loader wrapping `llama-cpp-python` with low-memory headroom guards and streaming inference.
- **`pithon/agent/`**: Autonomous personal agent subsystem:
  - `telegram_bot.py`: Telegram polling interface, command dispatch, and proactive messaging.
  - `web.py`: Embedded, self-hosted web companion UI and REST API.
  - `storage.py` & `markdown_store.py`: Dual-layer state persistence (SQLite for relational state, Human-readable Markdown files for persona, tasks, briefings, and notes).
  - `tools.py`, `calc.py`, `weather.py`, `search.py`, `calendar.py`, `image.py`: Modular agent tool executors.
- **`pithon/cli.py`**: Command-line entry points (`khepri pipe`, `khepri chat`, `khepri serve`).
- **`tests/`**: Comprehensive pytest test suite.

---

## Hardware & Performance Constraints

Khepri is targeted at single-board computers with constrained RAM. All contributions must respect our performance budgets:
1. **RAM Footprint:** The complete runtime (with a 0.5B quantized GGUF model loaded) must maintain a peak resident memory (RSS) of **< 750 MB**.
2. **Deterministic Fallbacks:** Fast-path operations (math, time queries, device stats) should bypass LLM inference entirely using deterministic regex routers.
3. **No Unbounded Memory Leaks:** Web and bot sessions must be bounded and garbage-collectible.

---

## Quality Standards & Verification

Before submitting code, ensure all automated verification steps pass locally:

### 1. Static Type Checking (`mypy`)
```bash
mypy pithon
```

### 2. Code Linting & Style (`ruff`)
```bash
ruff check pithon tests
```

### 3. Bytecode Compilation
```bash
python3 -m compileall pithon tests
```

### 4. Automated Unit Tests
```bash
pytest tests/ -m "not e2e" -v
```

---

## Submitting a Pull Request

1. **Commit message convention:** Write clear, concise commit messages following Conventional Commits (e.g. `feat(agent): ...`, `fix(engine): ...`, `docs: ...`, `ci: ...`).
2. **Fill out the PR template:** When opening a PR, complete all fields in the pull request template, including test evidence and platform verification.
3. **Keep PRs focused:** Submit small, targeted PRs rather than monolithic changes.

Thank you for helping make private, low-power AI accessible to everyone!
