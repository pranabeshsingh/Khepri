# Telegram Commands & Native Tool Calling

Khepri features a hybrid interaction layer: you can either execute deterministic slash commands or chat naturally while the 0.5B model routes function calls behind the scenes.

---

## 1. Slash Commands Reference

| Command | Syntax Example | Description | Execution Path |
| :--- | :--- | :--- | :--- |
| `/chat` | `/chat Explain TCP 3-way handshake in 3 bullet points` | Direct prompt to local 0.5B SLM | `pithon-daemon` inference |
| `/task` | `/task Deploy Khepri v0.2 in 45m` | Add scheduled task or reminder | SQLite task store + cron |
| `/tasks` | `/tasks` | List pending tasks and reminders | SQLite queries |
| `/weather` | `/weather Kolkata` | Live temperature, humidity, wind & forecast | Instant `wttr.in` API (0 API keys) |
| `/calc` | `/calc (1024 * 16) / 2` | Safe arithmetic evaluation | Python AST parser (Zero hallucinations) |
| `/note` | `/note Pi Config: Host IP 192.168.1.50` | Store note in markdown memory | `data/notes/*.md` filesystem |
| `/search` | `/search Docker cgroup memory limit` | Search local notes + DuckDuckGo web | Hybrid note + DuckDuckGo engine |
| `/status` | `/status` | System health, RAM RSS, active tasks, uptime | Linux OS `/proc/meminfo` & Docker |
| `/help` | `/help` | Display interactive cheat sheet | In-memory reference card |

---

## 2. Natural Language Tool Calling

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

## 3. Whitelist Security & Noise Filtration

* **Private Admin Whitelist:** Only the user matching `TELEGRAM_ADMIN_CHAT_ID` can trigger inference or view data.
* **Unauthorized Access:** Any incoming message from unknown user IDs receives:
  `⛔ Access Denied. Your chat ID is not authorized.`
* **Silent Digest Channel (`TELEGRAM_REPORT_CHAT_ID`):** Periodic analytical summaries are pushed here. Inbound messages from channels are discarded without CPU overhead.
