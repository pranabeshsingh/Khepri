# Telegram Commands & Native Tool Calling

Khepri features a multi-tiered interaction layer: deterministic slash commands, quick BotFather action registration, a sub-3ms rule-based fast-path router, local edge image processing & OCR, and natural conversational tool calling powered by Qwen2.5-0.5B.

---

## 1. Quick BotFather Command Setup

When configuring your bot in Telegram, open **[@BotFather](https://t.me/BotFather)**, send `/setcommands`, select your bot, and send this exact block:

```text
start - Open Khepri and view quick menu
help - Show all commands and features
briefing - Daily briefing (weather, news, milestones, quote)
calendar - View upcoming meetings and set ICS sync URL
pdf - Convert attached photo(s) to PDF document
compress - Compress attached photo to WebP format
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

---

## 2. Slash Commands Reference

| Command | Syntax Example | Description | Execution Path |
| :--- | :--- | :--- | :--- |
| `/start` | `/start` | Open welcome greeting & quick interactive menu | Telegram API inline keyboard |
| `/help` | `/help` | Display interactive cheat sheet & commands | In-memory reference card |
| `/briefing` | `/briefing` | Daily briefing: weather, top 10 news (5 local, 3 national, 2 world), milestones, quote, tasks | Aggregated RSS & storage engine |
| `/calendar` | `/calendar [set <url> \| alert <mins> \| sync]` | View upcoming meetings, configure open ICS feed URL, adjust alert lead time | Zero-dependency RFC 5545 parser & scheduler |
| `/pdf` | Attach photo with `/pdf` | Stitch & convert photo(s) into downloadable PDF document | In-memory Pillow PDF engine |
| `/compress` | Attach photo with `/compress` | Compress & resize photo to optimized WebP format | Pillow WebP encoder |
| `/init` | `/init` | Setup onboarding profile wizard (name, location, preferences) | Hybrid `data/profile.md` + SQLite engine |
| `/clear` | `/clear` | Clear conversation context memory turns | SQLite context reset engine |
| `/time` | `/time` | Current date, time, weekday, and configured timezone | Fast-path temporal grounder |
| `/tasks` | `/tasks` (or `/todo`) | List pending tasks and reminders with completion toggles | Hybrid `data/tasks.md` + SQLite store |
| `/add` | `/add Deploy v0.2 tomorrow at 5pm` | Create a new task or schedule a reminder (or `/task`) | Hybrid `data/tasks.md` + natural parser |
| `/timer` | `/timer 15m Pasta` | Start a countdown alert timer | Background cron scheduler |
| `/weather` | `/weather Tokyo` | Live temperature, humidity, wind & forecast | Fast-path `wttr.in` API (0 API keys) |
| `/calc` | `/calc (1024 * 16) / 2` | Safe arithmetic evaluation | Fast-path Python AST (Zero hallucinations) |
| `/notes` | `/notes` | Browse saved markdown knowledge notes | `data/notes/*.md` filesystem |
| `/note` | `/note server-ip 192.168.1.50` | Store a note or document into markdown memory | `data/notes/*.md` filesystem |
| `/search` | `/search Docker cgroup memory limit` | Search DuckDuckGo web results | Instant DuckDuckGo search engine |
| `/status` | `/status` | System health, RAM RSS, active tasks, uptime | Fast-path Linux OS `/proc/meminfo` & Docker |
| `/poll` | `/poll "Meeting Time?" "10 AM" "2 PM"` | Launch native Telegram interactive poll | Native Telegram Poll API |
| `/chat` | `/chat Explain TCP handshake in 3 bullets` | Direct query to local 0.5B SLM | `pithon-daemon` llama.cpp engine |

---

## 3. Local Edge Image Processing & OCR

Send any photo directly to Khepri on Telegram:

* **Terminal Error Diagnosis:** Snap a photo of your screen or terminal error trace with a question (*"How do I fix this?"*). Khepri executes local C++ Tesseract OCR, extracts the stack trace, and injects it into Qwen for an immediate technical fix.
* **Whiteboard & Document Digitization:** Send a photo with caption `/note Architecture Draft` ➔ Khepri extracts the handwritten or printed text and writes `data/notes/architecture-draft.md`.
* **Image to PDF (`/pdf`):** Convert photos into clean, downloadable PDF documents in <15ms.
* **Image Compression (`/compress`):** Automatically resizes and compresses oversized photos into lightweight WebP format.
* **4GB Pi 4 Vision Architecture:** Engineered using lightweight Tesseract OCR (~20MB RAM) and SmolVLM-500M hooks, ensuring total system memory never exceeds the 4GB Raspberry Pi 4 budget.

---

## 4. Deterministic Fast-Path Router (<3ms Latency)

Small language models (0.5B) can occasionally misformat JSON tool calls or consume precious CPU cycles on simple requests. Khepri includes a deterministic rule-based fast-path router in `router.py` that intercepts high-frequency queries before they ever touch the LLM:

* **Time & Date:** *"What time is it?"*, *"current time"*, *"today's date"* ➔ Sub-millisecond timezone-grounded clock.
* **Calendar & Agenda:** *"What is in my agenda?"*, *"Any calls today?"*, *"Show my schedule"* ➔ Queries upcoming calendar meetings with clickable direct video join links.
* **Weather:** *"How's the weather in Tokyo?"*, *"is it raining in Bengaluru"* ➔ Queries `wttr.in/<city>?format=j1` directly, returning structured live metrics without hallucinations.
* **AST Math & Arithmetic:** *"Calculate 450 * 1.18 + 32"* ➔ Evaluates safely with Python AST parser (100% precision).
* **Task Additions:** *"add task: Review PR 42"*, *"remind me to call John"* ➔ Synchronizes directly into `data/tasks.md` and database.
* **Notes Search:** *"search notes: deploy"*, *"notes about docker"* ➔ Scans `data/notes/` filesystem.
* **Status & Telemetry:** *"system status"*, *"health"*, *"uptime"* ➔ Immediate container and host telemetry report.

---

## 5. Daily Briefing Engine (`/briefing`)

Khepri generates a comprehensive daily briefing combining multiple edge data sources:
* **Personalized Header:** Addressed to the user's name from `data/profile.md`, exact date, and timezone.
* **Home City Weather:** Live weather from `wttr.in` for the user's home location.
* **Top 10 Curated Headlines:**
  * 📍 **5 Local News** (tailored to user's registered city)
  * 🇮🇳 **3 National News** (India headlines)
  * 🌐 **2 World News** (international headlines)
  * Deduplicated across sections with zero external API keys needed.
* **Interesting About Today:** Historical or scientific milestone for the calendar day.
* **Thought for Today:** Curated inspiring quote and philosophical wisdom.
* **Today's Agenda & Tasks:** Synchronized calendar calls with video links and pending tasks.
* **Edge Container Health:** System status and inference engine health.
* **Archival:** Every briefing is automatically archived in Markdown format at `data/briefings/YYYY-MM-DD.md`.

---

## 6. Automated Lifecycle Schedules

* **05:00 AM — Nightly Memory Compactor:** Background cron job reviews the previous day's conversations, extracts key technical decisions and user preferences, and writes a structured summary into `data/notes/daily_summary_YYYY-MM-DD.md`.
* **09:00 AM — Morning Daily Briefing:** Weather forecast, top 10 deduplicated news headlines, historical milestones, philosophical thought, agenda, and pending tasks.
* **07:30 PM (19:30) — Evening Wrap-Up & Tomorrow Preview:** Productivity recap (completed vs pending tasks) and preview of tomorrow's first scheduled meetings.
* **1-Minute Calendar Alert Tick:** Proactively pings Telegram when meetings are approaching (default: 10 minutes prior).
* **5-Minute Calendar Sync:** Synchronizes with open ICS calendar feeds using MD5 delta checks.

---

## 7. Whitelist Security & Noise Filtration

* **Private Admin Whitelist:** Only the user matching `TELEGRAM_ADMIN_CHAT_ID` can trigger inference or view data.
* **Unauthorized Access:** Any incoming message from unknown user IDs is silently rejected or receives an access denied notice.
* **Silent Digest Channel (`TELEGRAM_REPORT_CHAT_ID`):** Periodic analytical summaries are pushed here. Inbound messages from channels are discarded without CPU overhead.
