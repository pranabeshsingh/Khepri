# Mini-OpenClaw Personal Agent System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a multi-functional personal AI agent ("Mini-OpenClaw") integrated with Pithon, featuring dynamic timezone grounding, DuckDuckGo web search, interactive Telegram bot interface with button callbacks and silent hourly digests, tasks/reminders engine, and a modern secure Web UI exposed at `https://pithon.trylocalhost.com`.

**Architecture:** A dedicated, lightweight `pithon-agent` micro-service container runs alongside the existing `pithon-daemon` inference engine in Docker Compose with strict cgroup limits (`cpus: 0.5`, `mem_limit: 512m`). The agent coordinates Telegram long-polling, DuckDuckGo retrieval, SQLite audit storage, minute/hourly schedulers, and an authenticated Web UI reverse-proxied by Host Nginx with Let's Encrypt SSL.

**Tech Stack:** Python 3.12, `aiohttp`, `sqlite3` (WAL mode), DuckDuckGo HTML / Instant search, Telegram Bot API (Inline Keyboards, Callbacks, Polls), Vanilla CSS / Semantic HTML5, Docker Compose, Nginx SSL.

## Global Constraints
- Target VM is a 2-core ARM Ampere VM (12 GB RAM) co-hosting an active OwnTracks server.
- Zero CPU/RAM starvation for OwnTracks: `pithon-agent` capped at 0.5 CPU and 512 MB RAM.
- Zero secrets committed to git: all credentials, tokens, passwords, and chat IDs loaded via uncommitted `.env`.
- Loopback isolation: Web UI binds internally and maps to `127.0.0.1:8091`.
- Telegram chat whitelist: only chat ID `357035668` allowed for interactive chat; group `-1001169201210` receives silent hourly digests only. All other chats dropped.
- Hourly digest must use `disable_notification=True`.

---

### Task 1: Dynamic Temporal Grounding (`pithon/agent/time_context.py`)

**Files:**
- Create: `pithon/agent/time_context.py`
- Test: `tests/test_agent_time_context.py`

**Interfaces:**
- Produces: `get_current_time_info(tz_name: str = "Asia/Kolkata") -> dict`
- Produces: `format_temporal_prompt_header(tz_name: str = "Asia/Kolkata") -> str`

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_time_context.py` asserting current time metadata (year, month, day, weekday, time, timezone offset) and prompt header formatting.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_time_context.py
```

- [ ] **Step 3: Implement `pithon/agent/time_context.py`**
Implement zoneinfo timezone resolution (defaulting to `Asia/Kolkata`), ISO timestamp generation, and formatted prompt header.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_time_context.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/time_context.py tests/test_agent_time_context.py
git commit -m "feat(agent): add dynamic temporal grounding for Asia/Kolkata timezone"
```

---

### Task 2: DuckDuckGo Search Integrator (`pithon/agent/search.py`)

**Files:**
- Create: `pithon/agent/search.py`
- Test: `tests/test_agent_search.py`

**Interfaces:**
- Produces: `should_search(query: str) -> bool`
- Produces: `search_duckduckgo(query: str, max_results: int = 3, timeout: float = 5.0) -> list[dict]`
- Produces: `format_search_context(results: list[dict], query: str) -> str`

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_search.py` testing intent heuristic detection (`should_search`), mock DuckDuckGo HTML/API parsing, snippet truncation, and context string formatting.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_search.py
```

- [ ] **Step 3: Implement `pithon/agent/search.py`**
Implement keyword intent heuristics, clean HTTP search fetching via standard library / `urllib`, HTML snippet cleanup, and structured prompt generation.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_search.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/search.py tests/test_agent_search.py
git commit -m "feat(agent): add duckduckgo search integration and prompt formatter"
```

---

### Task 3: SQLite Audit & State Storage (`pithon/agent/storage.py`)

**Files:**
- Create: `pithon/agent/storage.py`
- Test: `tests/test_agent_storage.py`

**Interfaces:**
- Produces: `Storage(db_path: str)`
- Methods:
  - `init_db()`: Creates `interactions`, `tasks`, `digests`, `sessions` tables with indexes.
  - `log_interaction(chat_id, user_id, prompt, search_query, search_results, response, latency_ms) -> int`
  - `get_interactions(limit=50, offset=0, search_term=None) -> list[dict]`
  - `create_task(chat_id, title, list_name="default", due_at=None) -> int`
  - `get_tasks(chat_id, list_name=None, include_completed=False) -> list[dict]`
  - `complete_task(task_id: int) -> bool`
  - `delete_task(task_id: int) -> bool`
  - `snooze_task(task_id: int, hours: int = 1) -> bool`
  - `get_pending_reminders(current_iso: str) -> list[dict]`
  - `mark_reminded(task_id: int)`
  - `log_digest(target_chat_id, summary_text, period_start, period_end, count) -> int`
  - `get_digests(limit=20) -> list[dict]`
  - `create_session(token: str, expires_in_sec: int) -> None`
  - `validate_session(token: str) -> bool`

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_storage.py` exercising SQLite schema initialization, interaction logging, task lifecycle, and session validation.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_storage.py
```

- [ ] **Step 3: Implement `pithon/agent/storage.py`**
Implement SQLite storage layer with WAL mode, thread-safe connections, and parameterized queries.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_storage.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/storage.py tests/test_agent_storage.py
git commit -m "feat(agent): add sqlite storage layer for interactions, tasks, digests, and sessions"
```

---

### Task 4: Tasks, Reminders & Lists Parser (`pithon/agent/tasks.py`)

**Files:**
- Create: `pithon/agent/tasks.py`
- Test: `tests/test_agent_tasks.py`

**Interfaces:**
- Consumes: `pithon.agent.time_context`, `pithon.agent.storage`
- Produces: `is_task_intent(text: str) -> bool`
- Produces: `parse_task_natural_language(text: str, daemon_url: str, tz_name: str) -> dict`
- Produces: `format_tasks_message(tasks: list[dict]) -> tuple[str, list[list[dict]]]` (text + inline buttons)

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_tasks.py` verifying task intent classification, JSON response extraction from mock daemon, and inline keyboard button generation.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_tasks.py
```

- [ ] **Step 3: Implement `pithon/agent/tasks.py`**
Implement task intent detection, SLM prompt formatting using `preset="reminder"`, fallback regex parser for explicit dates, and Telegram inline keyboard generation.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_tasks.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/tasks.py tests/test_agent_tasks.py
git commit -m "feat(agent): add natural language task parser and inline button formatter"
```

---

### Task 5: Interactive Telegram Bot Router (`pithon/agent/telegram_bot.py`)

**Files:**
- Create: `pithon/agent/telegram_bot.py`
- Test: `tests/test_agent_telegram.py`

**Interfaces:**
- Consumes: `pithon.agent.storage`, `pithon.agent.search`, `pithon.agent.time_context`, `pithon.agent.tasks`
- Produces: `TelegramBot(token, admin_chat_id, report_chat_id, storage, daemon_url)`
- Methods:
  - `handle_message(message: dict) -> None`
  - `handle_callback_query(callback_query: dict) -> None`
  - `send_message(chat_id, text, reply_markup=None, disable_notification=False) -> dict`
  - `send_poll(chat_id, question, options) -> dict`
  - `poll_updates() -> None`

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_telegram.py` with mock Telegram API responses testing:
  - Acceptance of admin chat `357035668`.
  - Inbound discard of report chat `-1001169201210`.
  - Discard of unknown chat IDs.
  - Callback queries: `done:<id>`, `snooze:<id>`.
  - Slash commands: `/time`, `/todo`, `/search`, `/poll`, `/status`.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_telegram.py
```

- [ ] **Step 3: Implement `pithon/agent/telegram_bot.py`**
Implement asynchronous long-polling router, typing action indicator, inline keyboards, callback query handler with `answerCallbackQuery` and `editMessageText`, and native poll creator.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_telegram.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/telegram_bot.py tests/test_agent_telegram.py
git commit -m "feat(agent): add interactive telegram bot router with inline keyboards and poll support"
```

---

### Task 6: Scheduler for Minute Reminders & Silent Hourly Digest (`pithon/agent/scheduler.py`)

**Files:**
- Create: `pithon/agent/scheduler.py`
- Test: `tests/test_agent_scheduler.py`

**Interfaces:**
- Consumes: `pithon.agent.storage`, `pithon.agent.telegram_bot`, `pithon.agent.time_context`
- Produces: `Scheduler(bot, storage, report_chat_id, admin_chat_id)`
- Methods:
  - `check_reminders_tick() -> int` (returns number of dispatched reminders)
  - `hourly_digest_tick() -> str` (compiles and sends silent digest via `disable_notification=True`)

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_scheduler.py` asserting reminder detection at scheduled minute and silent hourly digest compilation.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_scheduler.py
```

- [ ] **Step 3: Implement `pithon/agent/scheduler.py`**
Implement async scheduler ticking every 60s for reminders and every 60m for silent hourly report formatting.

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_scheduler.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/scheduler.py tests/test_agent_scheduler.py
git commit -m "feat(agent): add async scheduler for minute reminders and silent hourly digests"
```

---

### Task 7: Modern Dark-Mode Web UI Server (`pithon/agent/web.py`)

**Files:**
- Create: `pithon/agent/web.py`
- Create: `pithon/agent/templates/` (HTML/CSS dashboard assets)
- Test: `tests/test_agent_web.py`

**Interfaces:**
- Consumes: `pithon.agent.storage`
- Produces: `make_web_app(storage, admin_password, daemon_url)`
- Endpoints:
  - `GET /login`, `POST /login`, `POST /logout`
  - `GET /` (Overview metrics & health)
  - `GET /interactions` (Audit log table + detail modal)
  - `GET /tasks`, `POST /api/tasks/toggle`, `POST /api/tasks/add`
  - `GET /digests` (Hourly reports archive)
  - `POST /api/playground` (Test prompt simulator)

- [ ] **Step 1: Write the failing test**
Create `tests/test_agent_web.py` verifying login authentication, session cookies, rate limiting, and dashboard rendering.

- [ ] **Step 2: Run test to confirm failure**
```bash
.venv/bin/pytest tests/test_agent_web.py
```

- [ ] **Step 3: Implement `pithon/agent/web.py` and UI templates**
Implement HTTP web server using Python standard library / `aiohttp` with rich dark-mode aesthetics (Inter font, glassmorphism, Slate palette, Emerald/Cyan badges, responsive layouts).

- [ ] **Step 4: Run tests to verify**
```bash
.venv/bin/pytest tests/test_agent_web.py -v
```

- [ ] **Step 5: Commit**
```bash
git add pithon/agent/web.py pithon/agent/templates tests/test_agent_web.py
git commit -m "feat(agent): add modern dark-mode web ui server with session auth"
```

---

### Task 8: Unified Agent Entrypoint, Dockerfile & Compose Configuration

**Files:**
- Create: `pithon/agent/main.py`
- Create: `Dockerfile.agent`
- Modify: `docker-compose.yml`
- Create: `.env.example`
- Modify: `.gitignore`
- Test: `tests/test_agent_e2e_integration.py`

- [ ] **Step 1: Implement `pithon/agent/main.py`**
CLI runner loading `.env`, initializing SQLite storage, starting Web UI server, and launching async Telegram bot & scheduler event loop.

- [ ] **Step 2: Create `Dockerfile.agent`**
Ultra-lightweight multi-stage Python 3.12-slim image (< 120 MB total) with minimal runtime dependencies.

- [ ] **Step 3: Update `docker-compose.yml`**
Add `pithon-agent` service:
```yaml
pithon-agent:
  build:
    context: .
    dockerfile: Dockerfile.agent
  container_name: pithon-agent
  restart: unless-stopped
  ports:
    - "127.0.0.1:8091:8080"
  volumes:
    - ./data:/app/data
  env_file:
    - .env
  cpus: 0.5
  mem_limit: 512m
  deploy:
    resources:
      limits:
        cpus: "0.5"
        memory: "512M"
  depends_on:
    - pithon
```

- [ ] **Step 4: Ensure `.env` is ignored and create `.env.example`**
Update `.gitignore` with `.env`, `data/`, `*.db`. Add `.env.example` with dummy values.

- [ ] **Step 5: Run integration test and verify all tests pass**
```bash
.venv/bin/pytest tests/ -v
```

- [ ] **Step 6: Commit and push**
```bash
git add .
git commit -m "feat(docker): package pithon-agent micro-service into docker-compose"
git push origin master
```

---

### Task 9: Remote VM Deployment, Nginx SSL & End-to-End Live Verification

**Steps:**
- [ ] **Step 1: Pull repository on remote VM**
```bash
ssh ubuntu@pithon.trylocalhost.com "cd /home/ubuntu/Pithon && git pull"
```

- [ ] **Step 2: Configure host `.env` file securely on VM**
Write `/home/ubuntu/Pithon/.env` with actual Telegram bot token, chat IDs, generated secure password, and permissions `0600`.

- [ ] **Step 3: Configure Host Nginx & Let's Encrypt SSL**
Create `/etc/nginx/sites-available/pithon.conf`, link to `sites-enabled/`, and run `certbot --nginx -d pithon.trylocalhost.com --non-interactive --agree-tos -m user@trylocalhost.com` (or reload nginx if certificates already exist).

- [ ] **Step 4: Build and launch `pithon-agent` container**
```bash
ssh ubuntu@pithon.trylocalhost.com "cd /home/ubuntu/Pithon && docker compose up -d --build pithon-agent"
```

- [ ] **Step 5: Verify container health & resource usage**
```bash
ssh ubuntu@pithon.trylocalhost.com "docker ps && docker stats --no-stream"
```
Confirm OwnTracks containers are 100% untouched and healthy, and `pithon-agent` is using < 50 MB RAM.

- [ ] **Step 6: Live Telegram & Web UI Verification**
- Send a test message and `/time` in Telegram chat `357035668`.
- Test `/search` with inline URL source buttons.
- Create a task and test the `[ ✅ Done ]` inline button.
- Trigger on-demand `/digest` and verify silent dispatch to group `-1001169201210`.
- Visit `https://pithon.trylocalhost.com`, log in with passphrase, and verify dashboard metrics and interaction log.
