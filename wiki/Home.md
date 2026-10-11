# 🪲 Khepri Documentation Wiki

Welcome to the official **Khepri** Wiki. Khepri is an ultra-lightweight autonomous Small Language Model (SLM) runtime and personal agent engineered for ARM hardware (Raspberry Pi 3/4/5) and low-resource cloud VPS instances.

---

## 📑 Wiki Navigation

* **[Telegram Bot Setup](Telegram-Bot-Setup)** — Step-by-step guide to creating a bot via `@BotFather`, obtaining tokens, getting your Admin Chat ID, and registering slash commands.
* **[Bot Commands & Tool Calling](Bot-Commands-and-Tools)** — Full reference of slash commands (`/chat`, `/task`, `/tasks`, `/weather`, `/calc`, `/note`, `/search`, `/status`) and natural language tool routing.
* **[Web Management Portal Guide](Web-Portal-Guide)** — Exploring the frosted glassmorphism dashboard, real-time telemetry, web chat, task kanban, and markdown memory editor.
* **[Architecture & Edge Deployment](Architecture-and-Deployment)** — Cgroup constraints, zero-swap ARM memory budgeting, loopback network security, and co-location with OwnTracks.

---

## ⚡ Quick Architecture Highlights

* **Model Runtime:** Qwen2.5-0.5B-Instruct (~350MB disk, ~480MB RAM) running locally via C++ `llama.cpp` bindings.
* **Autonomous Agent:** Zero external cloud API requirements for tools (deterministic `wttr.in` weather, Python AST arithmetic, DuckDuckGo instant answers, SQLite task store, markdown note system).
* **Security Whitelist:** Strict Chat ID whitelisting ensures only authorized users can invoke inference or access data.
