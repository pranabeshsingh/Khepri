<div align="center">
  <img src="assets/khepri-logo.svg" alt="Khepri Logo" width="130" height="130" />
  <h1>Khepri</h1>
  <p><strong>Autonomous Small Language Model (SLM) Runtime & Personal Agent for ARM & Low-Power Hardware</strong></p>

  <p>
    <a href="https://github.com/pranabeshsingh/Khepri/actions/workflows/ci.yml"><img src="https://github.com/pranabeshsingh/Khepri/actions/workflows/ci.yml/badge.svg" alt="CI Status" /></a>
    <a href="https://github.com/pranabeshsingh/Khepri/actions/workflows/docker.yml"><img src="https://github.com/pranabeshsingh/Khepri/actions/workflows/docker.yml/badge.svg" alt="Docker Build CI" /></a>
    <a href="https://github.com/pranabeshsingh/Khepri/actions/workflows/security.yml"><img src="https://github.com/pranabeshsingh/Khepri/actions/workflows/security.yml/badge.svg" alt="Security Scan" /></a>
    <a href="https://github.com/pranabeshsingh/Khepri/actions/workflows/codeql.yml"><img src="https://github.com/pranabeshsingh/Khepri/actions/workflows/codeql.yml/badge.svg" alt="CodeQL" /></a>
    <img src="https://img.shields.io/badge/RAM_Budget-%3C_550_MB_RSS-06b6d4" alt="RAM Budget" />
    <img src="https://img.shields.io/badge/Python-3.10_%7C_3.11_%7C_3.12-38bdf8" alt="Python Versions" />
    <img src="https://img.shields.io/badge/License-Apache--2.0-fbbf24" alt="License" />
  </p>

  <p>
    <a href="https://github.com/pranabeshsingh/Khepri/wiki"><strong>Explore the Wiki »</strong></a> •
    <a href="https://github.com/pranabeshsingh/Khepri/wiki/Telegram-Bot-Setup">Telegram Setup</a> •
    <a href="https://github.com/pranabeshsingh/Khepri/wiki/Bot-Commands-and-Tools">Commands & Tools</a> •
    <a href="https://github.com/pranabeshsingh/Khepri/wiki/Web-Portal-Guide">Management Portal</a> •
    <a href="https://github.com/pranabeshsingh/Khepri/wiki/Architecture-and-Deployment">Architecture</a>
  </p>
</div>

---

<p align="center">
  <img src="assets/khepri-cover.jpg" alt="Khepri Concept Banner" width="600" />
</p>

## Overview

**Khepri** (*named after the ancient solar scarab rolling dawn intelligence*) is an ultra-lightweight autonomous AI runtime engineered for resource-constrained edge environments (Raspberry Pi 3/4/5) and low-resource cloud VPS instances (Oracle Cloud 2-core ARM Ampere A1, Hetzner, AWS Graviton).

It pairs an in-memory **0.5B instruction-tuned SLM** with a full-fledged **personal agent**:
* 🤖 **Telegram Assistant:** Whitelisted private bot with native tool calling, background scheduler, and hourly digests.
* 🖥️ **Management Portal:** Premium frosted glassmorphism dark-mode UI with live hardware telemetry, web chat, task kanban, and markdown memory editor.
* 🛠️ **Deterministic Tools:** Live weather (`wttr.in`), exact AST math parsing, scheduled reminders, and DuckDuckGo instant search with zero cloud API keys.
* 🧠 **Markdown Memory:** Stores knowledge persistently in structured markdown files (`data/notes/*.md`).
* 🔒 **Zero Resource Starvation:** Strict Linux cgroup CPU & RAM caps guarantee uninterrupted operation for co-located workloads (OwnTracks, MQTT brokers, databases).

---

## Architecture

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

## Telegram Bot & Native Tools

Khepri acts as an always-on personal companion through Telegram. You can execute slash commands or simply speak in natural language.

### Supported Commands

| Command | Syntax | Description |
| :--- | :--- | :--- |
| `/start` | `/start` | Open welcome greeting & quick interactive menu |
| `/help` | `/help` | Display interactive cheat sheet |
| `/briefing` | `/briefing` | Daily briefing: weather, top 10 news (5 local, 3 national, 2 world), milestones, quote, tasks |
| `/calendar` | `/calendar`, `/calender`, `/agenda`, `/calendar set <url>`, `/calendar alert <mins>`, `/calendar sync` | View upcoming meetings & calls, set 5-min open ICS sync URL, configure reminder lead time |
| `/init` | `/init` | Setup onboarding profile wizard (name, home location, digest time, focus) |
| `/clear` | `/clear` (or `/reset`) | Clear conversation context memory turns |
| `/time` | `/time` | Current date, time, weekday, and configured timezone |
| `/tasks` | `/tasks` (or `/todo`) | List pending tasks and reminders with completion toggles |
| `/add` | `/add Deploy v0.2 tomorrow at 5pm` | Create a new task or scheduled reminder (or `/task`) |
| `/timer` | `/timer 15m Pasta` | Start countdown timer alert |
| `/weather` | `/weather Kolkata` | Live temperature, humidity & wind (`wttr.in`) |
| `/calc` | `/calc (450 * 1.18) + 32` | Safe deterministic arithmetic evaluation |
| `/notes` | `/notes` | Browse saved markdown knowledge notes |
| `/note` | `/note Server: Oracle ARM 24GB` | Save key/value note into markdown memory |
| `/search` | `/search Docker cgroup memory limit` | Search web results via DuckDuckGo |
| `/status` | `/status` | System health, RAM RSS, active tasks, uptime |
| `/poll` | `/poll "Meeting Time?" "10 AM" "2 PM"` | Native Telegram interactive poll |
| `/chat` | `/chat Explain Raft consensus in 3 sentences` | Direct query to local 0.5B SLM |
| `/pdf` | Attach photo with `/pdf` | Stitch & convert photo(s) into downloadable PDF document |
| `/compress` | Attach photo with `/compress` | Compress & resize image to optimized WebP format |

<details>
<summary>📋 <strong>BotFather Command Setup Block (Click to Expand)</strong></summary>

Copy and send this directly to [@BotFather](https://t.me/BotFather) after typing `/setcommands`:

```text
start - Open Khepri and view quick menu
help - Show all commands and features
briefing - Daily briefing (weather, top 10 news, facts, thought)
calendar - View upcoming meetings and set ICS sync URL
agenda - View today's schedule and meeting links
init - Setup personal profile and preferences
clear - Clear conversation context memory
time - Current date, time, and timezone
tasks - View active tasks and reminders
add - Add a new task or scheduled reminder
timer - Start a countdown timer
weather - Live weather forecast for a city
calc - Evaluate mathematical expression
notes - Browse saved markdown notes
note - Save a new note into memory
search - Search web results via DuckDuckGo
status - View system and inference health
poll - Create an interactive group poll
chat - Query local 0.5B AI model
```

</details>

### 📰 Personalized Daily Briefings (`/briefing`)
Triggered via `/briefing`, daily morning schedule (9:00 AM), or conversational queries (*"Give me today's briefing"*):
* **Personalized Greeting & Temporal Grounding:** Greeted with name from profile, exact date & local timezone.
* **Home City Weather:** Live temperature, condition, humidity, and wind.
* **Top 10 Curated Headlines:** 5 local news (tailored to user city), 3 national (India), and 2 world news via deduplicated zero-key RSS feeds.
* **Interesting About Today:** Historical or scientific milestone that happened on this day in history.
* **Thought for Today:** Curated inspiring quote and philosophical wisdom.
* **Tasks & Edge Health:** Active tasks overview and edge container health status.

### 📅 Calendar Sync & Meeting Alerts (`/calendar`, `/agenda`)
Triggered via `/calendar`, `/calender`, `/agenda`, or natural conversational questions (*"What is in my agenda?"*, *"Any calls today?"*, *"Show my schedule"*):
* **Multi-Provider ICS Sync:** Continuous, zero-dependency RFC 5545 iCalendar engine synchronizing every 5 minutes with any open `.ics` / `webcal://` link (Microsoft Outlook 365, Google Calendar, Apple iCloud, Proton, Fastmail).
* **MD5 Checksum Caching:** Bandwidth and CPU are conserved via MD5 digest verification—if the calendar has not changed on the remote server, re-parsing is bypassed entirely.
* **Instant Video Meeting Extraction:** Automatically parses video conferencing links (Microsoft Teams, Zoom, Google Meet, Webex) and formats them into clean 1-click Join buttons.
* **Proactive Telegram Alerts:** Sends an interactive notification to your Telegram chat before your meeting starts (default 10 mins, configurable via `/calendar alert <mins>`). Includes a 1-click **Join Meeting** URL button and a **Dismiss** acknowledgment button.
* **Daily Briefing Integration:** Seamlessly embeds today's scheduled meetings directly into the morning `/briefing`.
* **Web Management Portal:** View upcoming meetings, trigger manual sync, and configure feed URLs via the Web UI (`http://127.0.0.1:8091`).

### 📸 Local Edge Image Processing & OCR
Send any photo directly to Khepri on Telegram:
* **Terminal Error Diagnosis:** Snap a photo of your screen or terminal error trace with a question (*"How do I fix this?"*). Khepri runs local OCR, extracts the error text, and passes it to Qwen for an instant fix.
* **Whiteboard & Document Digitization:** Send a photo with caption `/note Architecture Draft` ➔ Khepri extracts the text and creates `data/notes/architecture-draft.md`.
* **Image to PDF (`/pdf`):** Convert photos into clean, downloadable PDF documents.
* **Image Compression (`/compress`):** Automatically resizes and compresses oversized images to lightweight WebP format.
* **4GB Pi 4 Vision Architecture:** Engineered to use lightweight C++ Tesseract OCR (~20MB RAM) and SmolVLM-500M, ensuring total system memory never exceeds the 4GB Raspberry Pi 4 budget.

### 🧠 Hybrid Markdown Memory Architecture
Instead of storing all user data in an opaque binary database, Khepri employs an open, human-readable file structure in `data/`:
* `data/profile.md`: User persona, communication style, and settings in YAML frontmatter + Markdown body (directly editable in nano or Obsidian).
* `data/tasks.md`: Standard GitHub-flavored `- [ ]` checklist synchronized bidirectionally with Telegram and the Web UI.
* `data/notes/*.md`: Persistent knowledge vault and documentation.
* `data/briefings/*.md`: Archived historical record of every morning and evening briefing.
* `pithon.db`: Lightweight SQLite retained exclusively for high-frequency calendar alert queries and session tokens.

### 🔄 Automated Lifecycle & Memory Compactor
* **05:00 AM — Nightly Memory Compactor:** Background cron job reviews the previous day's conversations, extracts key technical decisions and user preferences, and writes a structured summary into `data/notes/daily_summary_YYYY-MM-DD.md`.
* **09:00 AM — Morning Daily Briefing:** Weather forecast, top 10 deduplicated news headlines, historical milestones, philosophical thought, and today's agenda.
* **07:30 PM (19:30) — Evening Wrap-Up & Tomorrow Preview:** Productivity recap (completed vs pending tasks) and preview of tomorrow's first scheduled meetings.

### Natural Language Interceptors
* **Calendar & Agenda:** *"What is in my agenda?"*, *"Any calls today?"*, *"Show my schedule"* ➔ Instantly queries upcoming calendar meetings with clickable direct video join links.
* **Weather:** *"How's the weather in Tokyo?"* ➔ Queries `wttr.in/Tokyo` directly, returning structured live metrics without web search hallucinations.
* **Math:** *"What is 1024 * 64?"* ➔ Evaluated deterministically with 100% precision.
* **Reminders:** *"Remind me to check server logs in 20 minutes"* ➔ Grounded target timestamp computed and scheduled automatically.

> 📖 **Full Setup Instructions:** See the [Telegram Bot Setup Guide](https://github.com/pranabeshsingh/Khepri/wiki/Telegram-Bot-Setup).

---

## Quickstart with Docker Compose

The recommended deployment method uses Docker Compose with preconfigured cgroup constraints.

### 1. Clone the Repository
```bash
git clone https://github.com/pranabeshsingh/Khepri.git
cd Khepri
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
nano .env
```
Fill in:
```bash
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
TELEGRAM_ADMIN_CHAT_ID="your_numeric_chat_id"
WEB_ADMIN_PASSWORD="set_a_secure_web_passphrase"
TIMEZONE="Asia/Kolkata"
# Optional: Open/Published ICS Calendar Feed URL (Outlook 365, Google Calendar, Apple iCloud)
CALENDAR_ICS_URL="https://outlook.office365.com/.../calendar.ics"
```

### 3. Launch Containers
```bash
docker compose up -d --build
```

The daemon will automatically download the default Qwen2.5-0.5B model (~350MB) on first start.

* **Daemon OpenAI API:** `http://127.0.0.1:8090/v1/chat/completions`
* **Management Web Portal:** `http://127.0.0.1:8091`

---

## CLI & Bare-Metal Usage

Khepri can also be installed as a local Python package on Raspberry Pi OS or Linux:

```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install llama-cpp-python (using official prebuilt CPU wheels) and Khepri package
pip install --upgrade pip
pip install --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu llama-cpp-python
pip install -e .

# Download model
./scripts/download_model.sh qwen models
```

### 1. Pipe Log Analysis (`khepri pipe`)
Directly diagnose application crash traces from `stdin`:
```bash
journalctl -u nginx -n 50 | khepri pipe "What caused the crash?"
```

### 2. Interactive Terminal Chat (`khepri chat`)
Launch a multi-turn terminal REPL over SSH:
```bash
khepri chat
```

### 3. Background Daemon (`khepri serve`)
Run a standalone loopback server:
```bash
khepri serve --port 8080 --model models/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

---

## Testing & Quality Assurance

```bash
# Run unit and security test suite (80+ tests)
pytest tests/ -m "not e2e" -v

# Run linting check
ruff check pithon tests
```

---

## Documentation & Wiki

Explore the complete documentation in the [Wiki](https://github.com/pranabeshsingh/Khepri/wiki):
* [Telegram Bot Setup Guide](https://github.com/pranabeshsingh/Khepri/wiki/Telegram-Bot-Setup)
* [Bot Commands & Tool Calling Reference](https://github.com/pranabeshsingh/Khepri/wiki/Bot-Commands-and-Tools)
* [Management Portal Guide](https://github.com/pranabeshsingh/Khepri/wiki/Web-Portal-Guide)
* [Architecture & Edge Deployment](https://github.com/pranabeshsingh/Khepri/wiki/Architecture-and-Deployment)

---

## Community & Contributing

* **[Contributing Guidelines](CONTRIBUTING.md)**: Development setup, coding standards, and pull request workflow.
* **[Code of Conduct](CODE_OF_CONDUCT.md)**: Standards for a welcoming and inclusive community.
* **[Accessibility Commitment](ACCESSIBILITY.md)**: Accessibility priorities, WCAG targets, and assistive tech guidance.
* **[Security Policy](SECURITY.md)**: Supported versions and private vulnerability disclosure.
* **[Discussions](DISCUSSIONS.md)**: Ask questions, share setups, and discuss ideas in [GitHub Discussions](https://github.com/pranabeshsingh/Khepri/discussions).

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
