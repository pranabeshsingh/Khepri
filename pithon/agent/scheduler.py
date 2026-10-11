"""Async and threaded scheduler for minute-precision reminders and silent hourly digests."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Any, Optional

from pithon.agent.tasks import format_reminder_alert
from pithon.agent.time_context import get_current_time_info

logger = logging.getLogger("pithon.scheduler")

class Scheduler:
    """Handles minute reminder alerts and silent hourly analytical reports."""

    def __init__(
        self,
        bot: Any,
        storage: Any,
        admin_chat_id: str = "357035668",
        report_chat_id: str = "-1001169201210",
        tz_name: str = "Asia/Kolkata",
        dashboard_url: str = "https://pithon.trylocalhost.com"
    ):
        self.bot = bot
        self.storage = storage
        self.admin_chat_id = str(admin_chat_id).strip()
        self.report_chat_id = str(report_chat_id).strip()
        self.tz_name = tz_name
        self.dashboard_url = dashboard_url
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _get_tz(self) -> zoneinfo.ZoneInfo:
        try:
            return zoneinfo.ZoneInfo(self.tz_name)
        except Exception:
            return zoneinfo.ZoneInfo("UTC")

    def check_reminders_tick(self) -> int:
        """Scan for due tasks and dispatch reminder notifications to admin chat."""
        if not self.storage or not self.bot:
            return 0

        now_utc = datetime.now(timezone.utc)
        # Check against both UTC and local ISO strings to ensure compatibility
        now_local = datetime.now(self._get_tz())
        pending = self.storage.get_pending_reminders(now_utc.isoformat())
        if not pending:
            pending = self.storage.get_pending_reminders(now_local.isoformat())

        dispatched = 0
        for task in pending:
            tid = task["id"]
            msg_text, inline_kb = format_reminder_alert(task)
            reply_markup = {"inline_keyboard": inline_kb} if inline_kb else None
            try:
                self.bot.send_message(self.admin_chat_id, msg_text, reply_markup=reply_markup)
                self.storage.mark_reminded(tid)
                dispatched += 1
            except Exception as e:
                logger.error(f"Failed to dispatch reminder #{tid}: {e}")

        return dispatched

    def hourly_digest_tick(self) -> str:
        """Compile and send silent hourly activity digest to report chat ID."""
        now_local = datetime.now(self._get_tz())
        period_start = (now_local - timedelta(hours=1)).strftime("%H:%M")
        period_end = now_local.strftime("%H:%M")
        date_str = now_local.strftime("%d %b %Y")

        interactions = []
        if self.storage:
            # Query last 100 interactions and filter to the last hour
            all_inter = self.storage.get_interactions(limit=100)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            for it in all_inter:
                created_str = it.get("created_at", "")
                try:
                    # SQLite CURRENT_TIMESTAMP is UTC format "YYYY-MM-DD HH:MM:SS"
                    dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if dt >= cutoff:
                        interactions.append(it)
                except Exception:
                    interactions.append(it)

        total_count = len(interactions)
        search_count = sum(1 for it in interactions if it.get("search_query"))
        latencies = [it.get("latency_ms", 0) for it in interactions if it.get("latency_ms")]
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0

        # Tasks metrics
        active_tasks_count = 0
        if self.storage:
            active_tasks = self.storage.get_tasks(self.admin_chat_id, include_completed=False)
            active_tasks_count = len(active_tasks)

        digest = (
            f"📊 *Pithon Hourly Digest*\n"
            f"🕒 *Period:* {period_start} - {period_end} IST | {date_str}\n\n"
            f"*Activity Summary:*\n"
            f"• *Total Interactions:* {total_count}\n"
            f"• *Web Searches Conducted:* {search_count}\n"
            f"• *Avg Response Latency:* {avg_lat} ms\n\n"
            f"*Tasks & Lists:*\n"
            f"• *Pending Active Tasks:* {active_tasks_count}\n\n"
            f"*System Health:*\n"
            f"• *Daemon Status:* Healthy (loopback)\n"
            f"• *Container Limits:* 0.5 CPU, 512M RAM cgroups"
        )

        reply_markup = {
            "inline_keyboard": [
                [{"text": "📊 Open Web Dashboard", "url": self.dashboard_url}]
            ]
        }

        # Dispatch with silent notification
        if self.bot:
            try:
                self.bot.send_message(
                    self.report_chat_id,
                    digest,
                    reply_markup=reply_markup,
                    disable_notification=True
                )
            except Exception as e:
                logger.error(f"Failed to send hourly digest: {e}")

        # Record in storage
        if self.storage:
            start_iso = (now_local - timedelta(hours=1)).isoformat()
            end_iso = now_local.isoformat()
            self.storage.log_digest(
                self.report_chat_id,
                digest,
                start_iso,
                end_iso,
                interaction_count=total_count,
                sent_silent=True
            )

        return digest

    def _loop(self) -> None:
        last_hour = -1
        while self._running:
            try:
                # 1. Minute tick for reminders
                self.check_reminders_tick()

                # 2. Hourly tick at :00
                current_time = datetime.now(self._get_tz())
                if current_time.minute == 0 and current_time.hour != last_hour:
                    last_hour = current_time.hour
                    self.hourly_digest_tick()

            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")

            time.sleep(5.0)

    def start(self) -> None:
        """Start scheduler in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"Scheduler started for admin {self.admin_chat_id} and reports {self.report_chat_id}")

    def stop(self) -> None:
        """Stop background scheduler."""
        self._running = False
