# Mini-OpenClaw Personal Agent System Specification

## 1. Overview & Goals
Transform Pithon into a lightweight, always-on personal AI assistant ("Mini-OpenClaw") running on an Oracle Cloud ARM VM. The system provides:
1. **Dynamic Temporal Awareness**: Accurate date, time, weekday, and timezone (`Asia/Kolkata`) injected into every prompt.
2. **DuckDuckGo Web Search**: Hybrid retrieval (natural language heuristic + explicit `/search` command) augmenting the 0.5B model with live external facts.
3. **Telegram Bot Interface**:
   - Private interactive chat restricted strictly to chat ID `<YOUR_ADMIN_CHAT_ID>`.
   - Hourly analytical digest dispatched with silent notifications (`disable_notification=True`) to group ID `<YOUR_REPORT_CHAT_ID>`.
   - All other chat IDs strictly and silently discarded.
4. **Tasks, Reminders & Lists Engine**:
   - Natural language task/reminder parsing using Pithon's `reminder` preset + fast slash commands (`/todo`, `/add`, `/done`, `/list`).
   - Minute-precision background scheduler delivering timely reminder alerts to chat ID `<YOUR_ADMIN_CHAT_ID>`.
   - Hourly digest includes tasks completed and upcoming tasks due within 3 hours.
5. **Modern Web UI**:
   - Hosted at `127.0.0.1:8091` and exposed via Host Nginx at `https://pithon.trylocalhost.com`.
   - Dark-mode dashboard featuring System Metrics, Interaction Explorer, Tasks & Lists Checklist, Digest Archive, and Live Playground.
   - Branded session login portal with rate limiting and secure HTTP-only session cookies.
6. **Zero-Secret Commitment & Cgroup Isolation**:
   - Strict adherence to zero secrets committed to Git (`.env` file managed exclusively on host/container).
   - Containerized alongside `pithon-daemon` with strict cgroup limits (`cpus: 0.5`, `mem_limit: 512m`) ensuring zero interference with co-located OwnTracks services.

---

## 2. Architecture & Service Boundaries

```
                 +-----------------------------------------+
                 |            Telegram Cloud               |
                 +--------------------+--------------------+
                                      |
                         (Long-Polling TLS)
                                      v
+-------------------------------------------------------------------------------+
| Container: pithon-agent (Python 3.12, cpus: 0.5, mem_limit: 512M)            |
|                                                                               |
|  +---------------------+   +---------------------+   +---------------------+  |
|  | telegram_bot.py     |   | scheduler.py        |   | web_server.py       |  |
|  | - Chat Whitelist    |   | - 60s Reminders     |   | - Dashboard API     |  |
|  | - Commands & Chat   |   | - 60m Silent Digest |   | - Session Auth      |  |
|  +----------+----------+   +----------+----------+   +----------+----------+  |
|             |                         |                         |             |
|             +-------------------------+-------------------------+             |
|                                       v                                       |
|  +-------------------------------------------------------------------------+  |
|  | agent_core.py                                                           |  |
|  | - Temporal Grounding (Asia/Kolkata)                                     |  |
|  | - DuckDuckGo Search Integrator (HTML / Instant API)                     |  |
|  | - Natural Language Task/Reminder Parser                                 |  |
|  +---------------------+--------------------+------------------------------+  |
|                        |                    |                                 |
|                        v                    v                                 |
|  +---------------------+------+      +------+------------------------------+  |
|  | SQLite Storage (/app/data) |      | Local HTTP Client                   |  |
|  | - interactions, tasks, etc.|      | Target: http://pithon-daemon:8080   |  |
|  +----------------------------+      +-------------------------------------+  |
+---------------------------------------------------|---------------------------+
                                                    | (Internal Loopback / Net)
                                                    v
+-------------------------------------------------------------------------------+
| Container: pithon-daemon (C++ Llama Runtime, cpus: 1.0, mem_limit: 2048M)    |
| - Listening on 127.0.0.1:8090 / pithon-daemon:8080                            |
| - Model: Qwen2.5-0.5B-Instruct-Q4_K_M.gguf                                    |
+-------------------------------------------------------------------------------+
```

---

## 3. Detailed Component Specifications

### 3.1. Temporal Grounding (`pithon/agent/time_context.py`)
- Reads configured `TIMEZONE` (default: `Asia/Kolkata`).
- Computes:
  - Formatted string: `Day, DD Month YYYY HH:MM:SS TZ` (e.g. `Sunday, 11 October 2026 15:40:00 IST`).
  - ISO timestamp: `YYYY-MM-DDTHH:MM:SS+05:30`.
- Injects a standard temporal block into every outgoing system prompt:
  ```text
  [Current System Time & Date]
  Current Time: Sunday, 11 October 2026, 15:40 IST
  Timezone: Asia/Kolkata (UTC+05:30)
  ```

### 3.2. DuckDuckGo Search Integrator (`pithon/agent/search.py`)
- **Trigger Strategy**:
  1. **Explicit**: Commands `/search <query>` or `/web <query>`.
  2. **Heuristic**: Regex and keyword classifier detecting queries requiring external real-time data (`today`, `yesterday`, `latest`, `news`, `weather`, `who is`, `what happened`, `score`, `price`, `release`, `current`).
- **Fetch Mechanism**:
  - Uses DuckDuckGo HTML / Instant Answers endpoint via `urllib.request` / `aiohttp`.
  - Zero browser dependencies (no Chromium, no Playwright).
  - Timeout: 5.0 seconds.
  - Extracts top 3 results: `title`, `snippet` (max 220 chars), `url`.
- **Prompt Augmentation**:
  ```text
  [Live Web Search Results for: "<query>"]
  1. Title: <title>
     Snippet: <snippet>
     URL: <url>
  2. ...
  [Instruction: Use the web search results above to answer accurately and cite the source.]
  ```

### 3.3. Tasks, Reminders & Lists Engine (`pithon/agent/tasks.py`)
- **Natural Language Parsing**:
  - If a user prompt indicates intent to schedule, remind, or record a task/list item:
  - Pithon SLM is prompted with `preset="reminder"` and temporal context:
    ```json
    {
      "task": "buy groceries",
      "due_time": "2026-10-12T17:00:00+05:30",
      "list_name": "groceries"
    }
    ```
- **Slash Commands**:
  - `/todo` or `/tasks`: Lists incomplete tasks with their numeric ID and due date.
  - `/add <title> [due]`: Adds an item directly.
  - `/done <id>`: Marks a task completed.
  - `/lists`: Displays list categories and item counts.
  - `/list <name>`: Displays items within a specific category.
- **Background Dispatcher (`pithon/agent/scheduler.py`)**:
  - Ticks every 60 seconds.
  - Finds tasks where `is_completed = 0`, `reminded = 0`, and `due_at <= current_time`.
  - Dispatches direct notification to chat ID `<YOUR_ADMIN_CHAT_ID>`:
    ```markdown
    ⏰ *Reminder Due Now!*
    📌 *Task:* Renew domain
    🕒 *Due:* 16:00 IST
    Reply `/done <id>` to mark complete.
    ```
  - Updates `reminded = 1`.

### 3.4. Telegram Bot Router (`pithon/agent/telegram_bot.py`)
- **Long-Polling**: Uses Telegram Bot API `getUpdates` with `timeout=30` handling both `message` and `callback_query` updates.
- **Chat Whitelist**:
  - `chat_id == <YOUR_ADMIN_CHAT_ID>`:
    - Process message, trigger `sendChatAction(action="typing")`, execute search/SLM pipeline, record interaction in SQLite, respond via `sendMessage` (chunked at 4000 characters).
  - `chat_id == <YOUR_REPORT_CHAT_ID>`:
    - Inbound messages silently ignored.
    - Destination for hourly digests only.
  - Any other `chat_id`:
    - Silently dropped.

#### Interactive Telegram UX (Inline Keyboards, Buttons & Polls)
- **Interactive Task Buttons**:
  - When listing tasks (`/todo`, `/tasks`) or dispatching scheduled reminders, messages include inline action buttons:
    `[ ✅ Done: #id ]` `[ ⏰ Snooze 1h: #id ]` `[ 🗑️ Delete: #id ]`
  - Clicking any button triggers a Telegram `callback_query`. The bot answers via `answerCallbackQuery(text="Task marked done! ✅")` and updates the message text in-place using `editMessageText` with strikethrough completion formatting.
- **Direct Source URL Buttons on Search Results**:
  - Whenever DuckDuckGo search results are referenced in a response, the bot appends inline URL buttons directly linking to the retrieved sources:
    `[ 🌐 1. <Site Name> ]` `[ 🌐 2. <Site Name> ]` `[ 🌐 3. <Site Name> ]`
  - Tapping opens the article directly in the user browser/in-app viewer.
- **Interactive Quick Action Menu (Reply Keyboard)**:
  - Persistent/collapsible menu with buttons for one-tap execution:
    `[ 📋 My Tasks ] [ 🔍 Search ] [ 🕒 Date & Time ] [ 📈 System Status ]`
- **Native Telegram Polls (`sendPoll`)**:
  - Command `/poll "Question" "Option 1" "Option 2" ...` creates an official interactive Telegram poll.
  - Natural language trigger: asking Pithon to "Create a poll for..." extracts the question and choices and calls `sendPoll`.
- **Hourly Digest Interactive Link**:
  - Every silent hourly digest includes an inline web app button:
    `[ 📊 Open Dashboard ](https://pithon.trylocalhost.com)`
- **Hourly Digest Dispatcher**:
  - Runs at minute `00` of every hour.
  - Aggregates activity from `[now - 1 hour, now]`:
    - Interaction count, searches executed, average latency.
    - Completed tasks & tasks due in next 3 hours.
    - System health snapshot (uptime, daemon RSS, CPU load).
  - Sends to `<YOUR_REPORT_CHAT_ID>` with `disable_notification=True`.

### 3.5. SQLite Storage (`pithon/agent/storage.py`)
- Path: `/app/data/pithon.db` (mounted to `./data` on host).
- Tables:
  1. `interactions`: `id`, `chat_id`, `user_id`, `prompt`, `search_query`, `search_results` (JSON), `response`, `latency_ms`, `created_at`.
  2. `tasks`: `id`, `chat_id`, `title`, `list_name`, `due_at`, `is_completed`, `reminded`, `created_at`.
  3. `digests`: `id`, `target_chat_id`, `summary_text`, `period_start`, `period_end`, `interaction_count`, `sent_silent`, `created_at`.
  4. `sessions`: `token`, `created_at`, `expires_at`.

### 3.6. Modern Web UI (`pithon/agent/web.py`)
- **Port**: Bound internally to `0.0.0.0:8080`, mapped to `127.0.0.1:8091` on host.
- **Design Tokens**:
  - Background: Deep Slate `#090d16` / `#0f172a`.
  - Cards: Semi-transparent glass with `#1e293b` borders.
  - Typography: Google Inter / modern system sans-serif.
  - Accents: Emerald `#10b981` (healthy/online), Cyan `#06b6d4` (searches), Indigo `#6366f1` (completions).
- **Views**:
  1. `/login`: Clean branded login card requesting passphrase (`WEB_ADMIN_PASSWORD`).
  2. `/`: Dashboard overview with real-time stats cards (daemon status, RAM usage, 24h interaction counters, tasks overview).
  3. `/interactions`: Filterable table of all interactions with detailed modal (raw prompt, search snippets with URLs, model output, latency).
  4. `/tasks`: Interactive task and list checklist (add task, toggle complete, filter by list).
  5. `/digests`: Archive of all hourly silent digests.
  6. `/playground`: Test prompt and DuckDuckGo search simulator in browser.

---

## 4. Host Nginx & Zero-Secret Security Configuration

### 4.1. Secrets Management
- All credentials stored in `/home/ubuntu/Pithon/.env` (mode `0600`):
  ```bash
  TELEGRAM_BOT_TOKEN="<YOUR_TELEGRAM_BOT_TOKEN>"
  TELEGRAM_ADMIN_CHAT_ID="<YOUR_ADMIN_CHAT_ID>"
  TELEGRAM_REPORT_CHAT_ID="<YOUR_REPORT_CHAT_ID>"
  WEB_ADMIN_PASSWORD="<generated-secure-passphrase>"
  TIMEZONE="Asia/Kolkata"
  PITHON_DAEMON_URL="http://pithon-daemon:8080"
  PORT="8080"
  ```
- `.env.example` committed to repo with placeholders; `.env` listed in `.gitignore`.

### 4.2. Host Nginx Site Configuration (`/etc/nginx/sites-available/pithon.conf`)
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name pithon.trylocalhost.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name pithon.trylocalhost.com;

    ssl_certificate /etc/letsencrypt/live/pithon.trylocalhost.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pithon.trylocalhost.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # HSTS & Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Verification & Testing Strategy
1. **Unit Tests (`tests/test_agent_*.py`)**:
   - `test_time_context.py`: Verify timezone calculations, format strings, and weekday logic.
   - `test_search.py`: Mocked DuckDuckGo queries verifying snippet parsing, timeouts, and prompt injection formatting.
   - `test_tasks.py`: Verify task creation, listing, completion toggles, and minute scheduler queries.
   - `test_telegram_whitelist.py`: Verify message acceptance from `<YOUR_ADMIN_CHAT_ID>`, rejection from `<YOUR_REPORT_CHAT_ID>`, and drop of untrusted IDs.
   - `test_web_auth.py`: Verify rate limiting, password validation, session token lifecycle, and unauthorized redirects.
2. **End-to-End Live Validation on VM**:
   - Test DuckDuckGo query via Telegram bot in chat `<YOUR_ADMIN_CHAT_ID>`.
   - Test silent hourly digest generation dispatched to group `<YOUR_REPORT_CHAT_ID>`.
   - Test Web UI login and dashboard rendering at `https://pithon.trylocalhost.com`.
   - Run `docker stats` to verify total memory overhead remains under 50 MB for the agent and OwnTracks continues unaffected.
