"""Unified entrypoint orchestrating Telegram Bot, background scheduler, and Web UI."""

import logging
import os
import sys
import threading
import time

from pithon.agent.storage import Storage
from pithon.agent.telegram_bot import TelegramBot
from pithon.agent.scheduler import Scheduler
from pithon.agent.web import create_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pithon.agent.main")

def load_env_file(path: str = ".env") -> None:
    """Load key-value environment variables from .env file without external dependencies."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        logger.info(f"Loaded environment variables from {path}")
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")

def main() -> None:
    """Start Mini-OpenClaw agent services."""
    load_env_file()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    report_chat_id = os.environ.get("TELEGRAM_REPORT_CHAT_ID", "").strip()
    admin_password = os.environ.get("WEB_ADMIN_PASSWORD", "pithon-secure-pass").strip()
    daemon_url = os.environ.get("PITHON_DAEMON_URL", "http://pithon:8080").strip()
    tz_name = os.environ.get("TIMEZONE", "Asia/Kolkata").strip()
    port = int(os.environ.get("PORT", "8080"))
    db_path = os.environ.get("DB_PATH", "data/pithon.db").strip()

    logger.info("Initializing Pithon Agent Storage...")
    storage = Storage(db_path)

    # 1. Initialize Telegram Bot
    bot = None
    if bot_token and bot_token != "dummy":
        logger.info(f"Initializing Telegram Bot for admin {admin_chat_id} and reports {report_chat_id}...")
        bot = TelegramBot(
            token=bot_token,
            admin_chat_id=admin_chat_id,
            report_chat_id=report_chat_id,
            storage=storage,
            daemon_url=daemon_url,
            tz_name=tz_name
        )
        t_bot = threading.Thread(target=bot.run_polling, daemon=True)
        t_bot.start()
        logger.info("Telegram Bot long-polling started in background thread.")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not provided. Telegram polling disabled.")

    # 2. Initialize Scheduler
    if bot:
        logger.info("Starting reminder and hourly digest scheduler...")
        scheduler = Scheduler(
            bot=bot,
            storage=storage,
            admin_chat_id=admin_chat_id,
            report_chat_id=report_chat_id,
            tz_name=tz_name
        )
        scheduler.start()

    # 3. Start Web UI Server (Main Thread)
    logger.info(f"Starting Web UI Server on 0.0.0.0:{port}...")
    server = create_web_server(
        storage=storage,
        admin_password=admin_password,
        host="0.0.0.0",
        port=port,
        daemon_url=daemon_url,
        tz_name=tz_name
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Pithon Agent services...")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
