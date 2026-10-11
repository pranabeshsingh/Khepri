# Management Portal Guide

Khepri includes a dark-mode web management portal designed with frosted glassmorphism, ambient aurora lighting, and live operational telemetry.

---

## 1. Accessing the Portal

The web portal is hosted by `pithon-agent` and bound internally to `127.0.0.1:8091` (or your reverse-proxied public domain, e.g. `https://khepri.trylocalhost.com` or custom subdomain).

### Authentication
* Enter the passphrase configured in your `.env` under `WEB_ADMIN_PASSWORD` (or `PORTAL_PASSPHRASE`).
* Successful authentication sets a secure `HttpOnly` session cookie (`khepri_session`).
* Direct API calls can also pass `Authorization: Bearer <passphrase>` or `?token=<passphrase>`.

---

## 2. Dashboard Sections & Tabs

### 📊 Overview & System Telemetry
* **Live Pulse Dot:** Green pulsating status indicator confirming real-time connectivity between `khepri-agent` and `khepri-daemon`.
* **Hardware & Memory Gauge:** Real-time RAM consumption, active model architecture (`Qwen2.5-0.5B-Instruct`), thread count (`2`), and batch sizing (`128`).
* **Active Tasks & Notes Counters:** Quick counts of unresolved tasks and stored markdown memory files.

### 💬 Live Web Chat
* Full conversational interface allowing direct testing of the local model without opening Telegram or terminal SSH.
* Supports system presets:
  * `General Assistant`
  * `Log Analyzer`
  * `Task Reminder`
  * `Weather Analyst`

### 📋 Task Kanban
* View all active and completed reminders.
* Add new tasks with ISO or relative timestamps.
* Check off completed tasks with instant persistence in SQLite (`/app/data/pithon.db`).

### 🧠 Markdown Memory Viewer
* Browse all `.md` files stored in `data/notes/`.
* Inspect raw markdown notes captured via Telegram `/note` command or natural language chat.
* Quick-search notes by title or content snippet.

---

## 3. Reverse Proxy Configuration (Nginx)

To expose the portal securely over HTTPS with Let's Encrypt:

```nginx
server {
    server_name khepri.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 443 ssl;
    # ssl_certificate and key paths...
}
```


### 📰 Daily Briefings
Trigger `/briefing` directly from the chat suggestion pills or fetch JSON from `/api/briefing`.
