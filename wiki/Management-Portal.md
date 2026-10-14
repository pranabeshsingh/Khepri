# Management Portal Guide

Khepri includes a dark-mode web management portal designed with frosted glassmorphism, ambient aurora lighting, dynamic SLM telemetry, interactive vision studios, and live operational intelligence.

---

## 1. Accessing the Portal

The web portal is hosted by `pithon-agent` and bound internally to `127.0.0.1:8091` (or your reverse-proxied public domain, e.g. `https://khepri.trylocalhost.com` or custom subdomain).

### Authentication
* Enter the passphrase configured in your `.env` under `WEB_ADMIN_PASSWORD` (or `PORTAL_PASSPHRASE`).
* Successful authentication sets a secure `HttpOnly` session cookie (`pithon_session`).
* Supports session expiration, auto-logout, and secure API validation.

---

## 2. Dashboard Studios & Interactive Navigation

The portal features 10 studios accessible through a mobile-scrollable glassmorphic pill bar:

### 📊 Overview & System Telemetry (`#tab-overview`)
* **Dynamic Model & Engine Pill:** Live active model badge displaying current inference model (e.g. `Qwen2.5-1.5B-Instruct` or `Qwen2.5-0.5B-Instruct`), active threads, and real-time loopback latency (`⚡ 1.4ms`).
* **Hardware & Memory Gauge:** Real-time RAM consumption, Linux cgroup memory limit bar, and host memory usage.
* **Active Tasks & Notes Counters:** Quick counts of unresolved tasks and stored markdown memory files.
* **Quick Task & Prompt Launcher:** Fast inputs for prompt execution and immediate checklist additions.

### 💬 Chat Studio (`#tab-chat`)
* Full conversational interface allowing direct testing of the local model without opening Telegram or terminal SSH.
* **Quick Suggestion Chips:** One-tap action chips for:
  * `🌤️ Local Weather`
  * `📅 Today's Agenda`
  * `🌅 Daily Briefing`
  * `📋 Active Tasks`
  * `⚡ System Health`
  * `🔍 Tech News`
* **Telegram Mirroring:** Optional toggle to sync conversation turns directly into your Telegram admin chat.
* **System Presets:** Switch system prompt modes (`General`, `Log Analyzer`, `Task Reminder`, `Weather Analyst`).

### 📅 Interactive Calendar & Agenda Studio (`#tab-calendar`)
* **Next Meeting Hero Banner:** Prominent hero card showing the next scheduled event with live countdown (`Starts in 25m` or `Meeting in Progress`).
* **1-Click Video Call Join:** Automatically detects Google Meet, Microsoft Teams, Zoom, or Webex video URLs and renders a high-visibility glowing `📹 Join Video Call` button.
* **Chronological Agenda Timeline:** Categorizes meetings into **Today's Schedule**, **Tomorrow's Schedule**, and **Upcoming Later This Week**.
* **Calendar Feed Manager:** Configure iCalendar (`.ics` / `webcal://`) URL and notification lead time (minutes) directly from the UI with instant `POST /api/calendar/config` persistence and manual feed sync.

### 👁️ Edge Vision & Image Tools Studio (`#tab-tools`)
* **Traceback & Screenshot OCR:** Drag-and-drop terminal tracebacks or error screenshots. Local OCR extracts text instantly with a 1-click **Diagnose in Chat** button that pre-populates Chat Studio with the error for immediate root-cause analysis.
* **Multi-Image PDF Compiler:** Multi-file drag-and-drop dropzone. Preview thumbnail gallery with reorder/remove controls, compiling images into a clean PDF document with instant browser download (`POST /api/tools/pdf`).
* **WebP Image Compressor:** Drop oversized images, adjust quality slider (10% to 95%) and max resolution (up to 1920px), and download optimized WebP images with live savings metrics (`POST /api/tools/compress`).

### 🌅 Daily Briefings & Intelligence (`#tab-briefings`)
* **Live Weather Header:** Real-time temperature, condition icon, humidity, and wind summary for your home city.
* **Active Briefing Viewer:** Formatted markdown reader rendering today's briefing with clickable source links for top curated news headlines, calendar agendas, and motivational quotes.
* **Historical Archive Browser:** Browse past daily briefing markdown files (`data/briefings/*.md`), preview historical records with one click, and copy markdown content (`GET /api/briefings/history`, `GET /api/briefings/content`).
* **On-Demand Generation:** Generate a fresh daily briefing on-demand via the `⚡ Generate Fresh Briefing` button (`GET /api/briefing`).

### ⚙️ Persona & Hybrid Memory Hub (`#tab-profile`)
* **Visual Profile Settings:** Manage Preferred Name, Home City, Local Timezone, Daily Briefing schedule, and Primary Focus domains.
* **Agent Persona Editor:** Edit the Markdown system instructions and communication rules directly; atomically updates `data/profile.md` frontmatter and markdown body (`POST /api/profile`).
* **Persona Presets:** 1-click presets for `⚡ Concise Engineer`, `👔 Executive Assistant`, and `💻 Pair Programmer`.
* **Storage Health:** Live database stats, notes vault size, and telemetry overview.

### 📋 Tasks & Timers (`#tab-tasks`)
* View all active and completed reminders.
* Add new tasks with category tags.
* Check off completed tasks with instant bidirectional synchronization into `data/tasks.md` and SQLite.

### 🧠 Markdown Memory Viewer (`#tab-notes`)
* Browse all `.md` files stored in `data/notes/`.
* Inspect and edit raw markdown notes captured via Telegram `/note` command or web portal.
* Quick-search notes by title or content snippet.

### 📜 Audit Log (`#tab-interactions`)
* Chronological table of all interactions across both Web and Telegram channels.
* Displays timestamps, prompt text, model response preview, and inference latency in milliseconds.
* Search and filter interactions instantly.

### 📰 Hourly Digests (`#tab-digests`)
* Overview of background hourly rollups and news digests.
