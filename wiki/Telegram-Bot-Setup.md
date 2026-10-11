# Telegram Bot Setup Guide

This guide walks you through creating your Telegram Bot, obtaining API credentials, retrieving your private Chat ID, and registering commands.

---

## 1. Create a Bot with @BotFather

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)** (look for the official blue verification checkmark).
2. Press **Start** or send `/start`.
3. Send the command:
   ```text
   /newbot
   ```
4. **Choose a Name**: Enter a display name for your assistant (e.g., `Khepri Assistant`).
5. **Choose a Username**: Enter a unique username ending in `bot` (e.g., `khepri_edge_bot` or `my_khepri_bot`).
6. **Save Your API Token**:
   BotFather will reply with your HTTP API token:
   ```text
   Use this token to access the HTTP API:
   8737152158:AAHc4H3KgnBPHE9q30pLy1e4Urlc_sHedyQ (example)
   ```
   > ⚠️ **IMPORTANT**: Never commit this token to Git or share it publicly! Keep it strictly in your `.env` file.

---

## 2. Retrieve Your Admin Chat ID

Khepri enforces a **strict whitelist security model**. Only your authorized Chat ID is permitted to execute commands, invoke LLM inference, or manage notes.

1. In Telegram, search for **[@userinfobot](https://t.me/userinfobot)** or **[@raw_data_bot](https://t.me/raw_data_bot)**.
2. Send `/start`.
3. The bot will reply with your account details:
   ```text
   Id: 357035668
   First name: Pranabesh
   Username: @...
   ```
4. Copy the numeric `Id` value. This is your `TELEGRAM_ADMIN_CHAT_ID`.

---

## 3. Register Slash Commands in Telegram

Registering slash commands makes them appear in the native Telegram popup menu whenever you type `/` in the chat.

1. Return to **[@BotFather](https://t.me/BotFather)**.
2. Send the command:
   ```text
   /setcommands
   ```
3. Select your Khepri bot from the list.
4. Copy and paste the following block in a single message:

```text
start - Open Khepri and view quick menu
help - Show all commands and features
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

5. BotFather will confirm: `Success! commands list updated.`

---

## 4. (Optional) Set Bot Profile Picture and Description

In **[@BotFather](https://t.me/BotFather)**:
* Send `/setuserpic`, select your bot, and upload `assets/khepri-cover.jpg` or `assets/khepri-logo.svg`.
* Send `/setdescription` to add an "About" overview:
  > *Khepri: Autonomous Edge SLM Assistant with native tool calling, markdown memory, and system diagnostics.*

---

## 5. Configure Your Host Environment

On your server or local Raspberry Pi, copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your editor:

```bash
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
TELEGRAM_ADMIN_CHAT_ID="your_numeric_admin_id"
TELEGRAM_REPORT_CHAT_ID="your_optional_group_id_or_leave_blank"
WEB_ADMIN_PASSWORD="your_secure_web_passphrase"
TIMEZONE="Asia/Kolkata"
```

Start the containers:

```bash
docker compose up -d
```

Open your bot in Telegram and send `/status` or `/help` to verify!
