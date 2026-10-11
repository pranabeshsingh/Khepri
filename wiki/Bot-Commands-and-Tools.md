# Telegram Commands & Native Tool Calling

Khepri features a hybrid interaction layer: deterministic slash commands, quick BotFather action registration, and natural conversational routing with native tool calling powered by Qwen2.5-0.5B.

---

## 1. Quick BotFather Command Setup

When configuring your bot in Telegram, open **[@BotFather](https://t.me/BotFather)**, send `/setcommands`, select your bot, and send this exact block:

```text
start - Open Khepri and view quick menu
help - Show all commands and features
briefing - Daily briefing (weather, top 10 news, facts, thought)
init - Setup personal profile and preferences
clear - Clear conversation context memory
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
| `/init` | `/init` | Setup onboarding profile wizard (name, location, preferences) | SQLite user profile engine |
| `/clear` | `/clear` | Clear conversation context memory turns | SQLite context reset engine |
| `/time` | `/time` | Current date, time, weekday, and configured timezone | Python `zoneinfo` temporal grounder |
| `/tasks` | `/tasks` (or `/todo`) | List pending tasks and reminders with completion toggles | SQLite task store (`/app/data/pithon.db`) |
| `/add` | `/add Deploy v0.2 tomorrow at 5pm` | Create a new task or schedule a reminder (or `/task`) | SQLite task store + natural parser |
| `/timer` | `/timer 15m Pasta` | Start a countdown alert timer | Background cron scheduler |
| `/weather` | `/weather Tokyo` | Live temperature, humidity, wind & forecast | Instant `wttr.in` API (0 API keys) |
| `/calc` | `/calc (1024 * 16) / 2` | Safe arithmetic evaluation | Python AST parser (Zero hallucinations) |
| `/notes` | `/notes` | Browse saved markdown knowledge notes | `data/notes/*.md` filesystem |
| `/note` | `/note server-ip 192.168.1.50` | Store a key/value or note into markdown memory | `data/notes/*.md` filesystem |
| `/search` | `/search Docker cgroup memory limit` | Search DuckDuckGo web results | Instant DuckDuckGo search engine |
| `/status` | `/status` | System health, RAM RSS, active tasks, uptime | Linux OS `/proc/meminfo` & Docker |
| `/poll` | `/poll "Meeting Time?" "10 AM" "2 PM"` | Launch native Telegram interactive poll | Native Telegram Poll API |
| `/chat` | `/chat Explain TCP handshake in 3 bullets` | Direct query to local 0.5B SLM | `pithon-daemon` llama.cpp engine |

---

---

## 2b. Daily Briefing Engine (`/briefing`)

Khepri generates a comprehensive daily briefing report combining multiple edge data sources:
* **Personalized Header:** Addressed to the user's name from profile, exact date, and timezone.
* **Home City Weather:** Live weather from `wttr.in` for the user's home location.
* **Top 10 Curated Headlines:**
  * 📍 **5 Local News** (tailored to user's registered city, e.g., Kolkata or Bengaluru)
  * 🇮🇳 **3 National News** (India headlines)
  * 🌐 **2 World News** (international headlines)
  * Deduplicated across sections with zero external API keys needed.
* **Interesting About Today:** Historical or scientific milestone for the calendar day.
* **Thought for Today:** Curated inspiring quote and philosophical wisdom.
* **Tasks & Schedule:** Count of pending items and top scheduled tasks.
* **Edge Container Health:** System status and inference engine health.

Triggerable manually via `/briefing`, via Telegram interactive buttons, Web Portal pill, or scheduled automatically every morning at 9:00 AM.

## 3. Natural Language Tool Calling

You do not need to memorize slash commands. The Khepri conversational router intercepts and fulfills queries automatically:

### 🌤️ Weather Intent Interceptor
* **User Input:** *"How is the weather in Tokyo right now?"*
* **Routing:** Intercepts location `Tokyo`, queries `wttr.in/Tokyo?format=j1`, returns structured live metrics (Temperature, Feels Like, Humidity, Condition) instantly without hallucinating or falling back to search engine SEO snippets.

### 🧮 Math & Arithmetic Interceptor
* **User Input:** *"Can you calculate 25 * 18.5 + 40?"*
* **Routing:** Evaluates expression deterministically using AST parser; returns `502.5` with 100% precision.

### ⏰ Scheduled Reminders & Timers
* **User Input:** *"Remind me to check server logs in 20 minutes"*
* **Routing:** Computes target timestamp grounded in your configured timezone (`Asia/Kolkata`); background scheduler triggers push notification when time expires.

### 📝 Markdown Memory Engine
* **User Input:** *"Save a note: SQLite database path is /app/data/pithon.db"*
* **Routing:** Writes file to `data/notes/sqlite_database_path.md`.
* **Subsequent Query:** *"Where is our SQLite database stored?"*
* **Routing:** Scans `data/notes/`, injects matching note context into model prompt, and answers accurately.

---

## 4. Whitelist Security & Noise Filtration

* **Private Admin Whitelist:** Only the user matching `TELEGRAM_ADMIN_CHAT_ID` can trigger inference or view data.
* **Unauthorized Access:** Any incoming message from unknown user IDs is silently rejected or receives an access denied notice.
* **Silent Digest Channel (`TELEGRAM_REPORT_CHAT_ID`):** Periodic analytical summaries are pushed here. Inbound messages from channels are discarded without CPU overhead.
