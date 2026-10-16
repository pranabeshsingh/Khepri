# 🪲 Khepri Documentation Wiki

Welcome to the official **Khepri** Wiki. Khepri is an ultra-lightweight autonomous Small Language Model (SLM) runtime and personal agent engineered specifically for ARM hardware (Raspberry Pi 4/5) and low-resource cloud VPS instances.

---

## 📑 Wiki Navigation

* **[Telegram Bot Setup](Telegram-Bot-Setup)** — Step-by-step guide to creating a bot via `@BotFather`, obtaining tokens, getting your Admin Chat ID, and registering slash commands.
* **[Bot Commands & Tool Calling](Bot-Commands-and-Tools)** — Full reference of slash commands (`/chat`, `/pdf`, `/compress`, `/calendar`, `/tasks`, `/weather`, `/calc`, `/notes`, `/search`, `/status`), local edge OCR, fast-path routing, and lifecycle schedules.
* **[Web Management Portal Guide](Web-Portal-Guide)** — Exploring the frosted glassmorphism dashboard, real-time telemetry, web chat, task kanban, and hybrid markdown file synchronization (`profile.md`, `tasks.md`, `briefings/`).
* **[Architecture & Edge Deployment](Architecture-and-Deployment)** — 4GB Raspberry Pi 4/5 memory budget, C++ Tesseract OCR optimization, cgroup constraints, zero-swap ARM memory management, loopback security, dual container layout, and the systemd bare-metal path.

---

## ⚡ Quick Architecture Highlights

* **Model Runtime:** Qwen2.5-0.5B-Instruct (~350MB disk, ~306MB RAM) running locally via C++ `llama.cpp` bindings.
* **Deterministic Fast-Path Router:** Sub-3ms rule-based routing for Time, Calendar, Weather, AST Math, and Task management—bypassing the 0.5B LLM entirely and saving CPU threads for complex reasoning.
* **Local Edge Image & Vision Processing:** System Tesseract OCR (~20MB RAM) for terminal error diagnosis and whiteboard transcription, Pillow for `/pdf` document stitching and `/compress` WebP optimization, with SmolVLM visual question-answering hooks.
* **Hybrid Markdown Memory Architecture:** Human-readable open filesystem memory (`data/profile.md`, `data/tasks.md`, `data/notes/*.md`, `data/briefings/*.md`) with SQLite retained strictly for 1-minute calendar alert caching and web sessions.
* **Automated Lifecycle Routines:** 05:00 AM Nightly Memory Compactor, 09:00 AM Morning Daily Briefing, and 07:30 PM Evening Wrap-Up & Tomorrow Preview.
* **Security Whitelist:** Strict Telegram Chat ID and bearer token whitelisting ensures only authorized users can invoke inference or access data.
