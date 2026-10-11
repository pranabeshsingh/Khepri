# Pithon GitHub Actions CI & ARM64 E2E Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-job GitHub Actions CI workflow with native ARM64 runners (`ubuntu-24.04-arm`) running real model downloads (SmolLM-135M & Qwen2.5-0.5B), live SSE streaming tests, and memory ceiling verification.

**Architecture:** A GitHub Actions workflow (`.github/workflows/ci.yml`) split into a fast cross-platform matrix unit test job (`ubuntu-latest` and `ubuntu-24.04-arm` across Python 3.10-3.12) and a dedicated live ARM64 inference job (`ubuntu-24.04-arm`). Models are cached with `actions/cache`. A dedicated pytest E2E suite (`tests/test_e2e_real_model.py`) marked with `@pytest.mark.e2e` exercises real token generation, piped log analysis, and live HTTP daemon streaming.

**Tech Stack:** GitHub Actions, `ubuntu-24.04-arm` runner, Python 3.10-3.12, `pytest`, `llama-cpp-python`, `actions/cache`, `actions/checkout`, `actions/setup-python`.

## Global Constraints

- **Platform Runner:** Live inference strictly targets `ubuntu-24.04-arm` to validate ARM NEON SIMD execution.
- **Cache Strategy:** `./models/` must be cached by hash of `scripts/download_model.sh` to keep CI runs under 2 minutes.
- **Test Separation:** E2E tests must be isolated via pytest markers (`@pytest.mark.e2e`) so fast unit tests can run anywhere without requiring 400 MB downloads.
- **Memory Ceiling:** E2E tests must explicitly assert peak RSS remains < 550 MB.

---

### Task 1: Update Model Downloader Script for Multi-Model Support

**Files:**
- Modify: `scripts/download_model.sh`

**Interfaces:**
- Produces: `./scripts/download_model.sh [smollm|qwen|all] [destination_dir]`

- [ ] **Step 1: Update `scripts/download_model.sh`**
  Support downloading `smollm` (SmolLM-135M-Instruct-Q4_K_M ~90MB), `qwen` (Qwen2.5-0.5B-Instruct-Q4_K_M ~350MB), or `all`.

- [ ] **Step 2: Test script argument parsing and idempotency**
  Verify `./scripts/download_model.sh --help` and path validation.

- [ ] **Step 3: Commit**
  `git add scripts/download_model.sh && git commit -m "feat(scripts): add multi-model support to download_model.sh"`

---

### Task 2: Pytest Configuration & Marker Separation

**Files:**
- Create: `pytest.ini`

**Interfaces:**
- Produces: Markers `unit` and `e2e` to cleanly separate offline unit tests from live model runs.

- [ ] **Step 1: Create `pytest.ini`**
  Register `e2e` marker description and set default test options.

- [ ] **Step 2: Verify default test run excludes nothing unless specified**
  Run `.venv/bin/pytest -m "not e2e"` to verify existing 21 unit tests execute.

- [ ] **Step 3: Commit**
  `git add pytest.ini && git commit -m "chore: configure pytest markers for unit and e2e"`

---

### Task 3: Comprehensive End-to-End Test Suite (`tests/test_e2e_real_model.py`)

**Files:**
- Create: `tests/test_e2e_real_model.py`

**Interfaces:**
- Produces:
  - `test_e2e_pipe_live_inference`: Tests real `pithon pipe` with a real model.
  - `test_e2e_server_live_streaming`: Boots daemon on dynamic port, streams tokens via SSE, validates JSON.
  - `test_e2e_memory_footprint`: Asserts process RSS < 550 MB during generation.

- [ ] **Step 1: Write `tests/test_e2e_real_model.py`**
  Implement test cases with `@pytest.mark.e2e`, locating any downloaded model in `./models/` or skipping if no model is present.

- [ ] **Step 2: Run pytest to verify skipped behavior when model absent**
  Run `.venv/bin/pytest tests/test_e2e_real_model.py -v`.

- [ ] **Step 3: Commit**
  `git add tests/test_e2e_real_model.py && git commit -m "feat(tests): implement comprehensive ARM64 E2E test suite"`

---

### Task 4: GitHub Actions Workflow (`.github/workflows/ci.yml`)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: Complete GitHub Actions CI pipeline with `unit-tests` matrix and `arm64-e2e-inference` runner.

- [ ] **Step 1: Create `.github/workflows/ci.yml`**
  Configure:
  - Job 1: `unit-tests` on `ubuntu-latest` and `ubuntu-24.04-arm` across Python 3.10, 3.11, 3.12.
  - Job 2: `arm64-e2e-inference` on `ubuntu-24.04-arm` with Python 3.12, actions/cache for `./models/`, model download, llama-cpp-python install, and live e2e pytest run.

- [ ] **Step 2: Validate YAML syntax**
  Check workflow file for valid YAML and GitHub Actions schema syntax.

- [ ] **Step 3: Commit**
  `git add .github/workflows/ci.yml && git commit -m "ci: add GitHub Actions workflow with native ARM64 runner and live model test"`
