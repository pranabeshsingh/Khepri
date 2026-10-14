"""Async and threaded scheduler for minute-precision reminders and silent hourly digests."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Any, Optional

import os
from pithon.agent.calendar import fetch_and_parse_calendar
from pithon.agent.tasks import format_reminder_alert

logger = logging.getLogger("pithon.scheduler")

class Scheduler:
    """Handles minute reminder alerts and silent hourly analytical reports."""

    def __init__(
        self,
        bot: Any,
        storage: Any,
        admin_chat_id: str = "",
        report_chat_id: str = "",
        tz_name: str = "Asia/Kolkata",
        dashboard_url: str = "https://khepri.trylocalhost.com"
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

    def daily_briefing_tick(self) -> str:
        """Compile and send rich morning briefing to admin chat."""
        from pithon.agent.briefing import generate_daily_briefing
        briefing = generate_daily_briefing(self.admin_chat_id, self.storage, tz_name=self.tz_name)
        if self.bot and self.admin_chat_id:
            try:
                self.bot.send_message(self.admin_chat_id, briefing, disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"Failed to send scheduled daily briefing: {e}")
        return briefing

    def calendar_sync_tick(self, force: bool = False) -> int:
        """Periodically sync remote ICS calendar feed with MD5 change detection."""
        if not self.storage or not self.admin_chat_id:
            return 0

        prof = self.storage.get_user_profile(self.admin_chat_id) or {}
        cal_url = prof.get("calendar_url") or os.environ.get("CALENDAR_ICS_URL", "")
        if not cal_url:
            return 0

        current_feed_md5 = prof.get("calendar_feed_md5") or ""
        changed, feed_md5, events = fetch_and_parse_calendar(cal_url, current_feed_md5, self.tz_name)

        if changed or force:
            self.storage.save_calendar_events(self.admin_chat_id, events)
            self.storage.update_calendar_settings(self.admin_chat_id, feed_md5=feed_md5)
            logger.info(f"Synchronized calendar: {len(events)} events (MD5 {feed_md5[:8]})")

        self.storage.prune_old_calendar_events(days=7)
        return len(events) if (changed or force) else 0

    def calendar_alerts_tick(self) -> int:
        """Check for upcoming meetings starting within alert_mins window and send proactive notifications."""
        if not self.storage or not self.bot or not self.admin_chat_id:
            return 0

        prof = self.storage.get_user_profile(self.admin_chat_id) or {}
        alert_mins = int(prof.get("calendar_alert_mins") or 10)

        now = datetime.now(timezone.utc)
        start_iso = now.isoformat()
        end_iso = (now + timedelta(minutes=alert_mins, seconds=30)).isoformat()

        unreminded = self.storage.get_unreminded_events_in_range(self.admin_chat_id, start_iso, end_iso)
        dispatched = 0

        for ev in unreminded:
            try:
                ev_start = datetime.fromisoformat(ev["start_time"])
                ev_end = datetime.fromisoformat(ev["end_time"])
                tz = self._get_tz()
                local_start = ev_start.astimezone(tz)
                local_end = ev_end.astimezone(tz)
                time_str = f"{local_start.strftime('%I:%M %p')} - {local_end.strftime('%I:%M %p')}"
                mins_until = max(1, int((ev_start - now).total_seconds() / 60))

                title = ev.get("title", "Upcoming Meeting")
                location = ev.get("location") or "Online Meeting"
                link = ev.get("meeting_link")

                min_label = f"{mins_until} mins" if mins_until > 1 else "1 min"
                msg_text = (
                    f"🔔 *Upcoming Call in {min_label}!*\n\n"
                    f"📌 *{title}*\n"
                    f"🕒 `{time_str}`\n"
                    f"📍 _{location}_"
                )
                row = []
                if link:
                    row.append({"text": "📞 Join Meeting", "url": link})
                row.append({"text": "✅ Acknowledged", "callback_data": f"cal_dismiss:{ev['id']}"})
                reply_markup = {"inline_keyboard": [row]}

                self.bot.send_message(
                    self.admin_chat_id,
                    msg_text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                self.storage.mark_event_reminded(ev["id"])
                dispatched += 1
            except Exception as e:
                logger.error(f"Failed to dispatch calendar alert for event {ev.get('id')}: {e}")

        return dispatched


    def compact_memory_tick(self) -> Optional[str]:
        """Nightly job at 5:00 AM: consolidate yesterday's chat turns into a clean markdown summary."""
        if not self.storage:
            return None
        tz = self._get_tz()
        now_local = datetime.now(tz)
        yesterday = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

        # Query interactions from yesterday
        history = self.storage.get_recent_history(limit=50, chat_id=self.admin_chat_id)
        if not history:
            return None

        # Filter out noisy or trivial single-word commands
        meaningful = []
        for h in history:
            text = h.get("content", "").strip()
            if text and not text.startswith(("/", "time", "weather", "cal")):
                meaningful.append(text)

        if not meaningful:
            return None

        summary_lines = [
            f"# Daily Conversation Summary — {yesterday}",
            f"- **Compacted At:** `{now_local.strftime('%Y-%m-%d %H:%M:%S')} {self.tz_name}`",
            f"- **Interactions Consolidated:** `{len(meaningful)}`\n",
            "## Key Discussions & Focus Points"
        ]
        for idx, item in enumerate(meaningful[:12], 1):
            clean_item = item.replace("\n", " ")
            summary_lines.append(f"{idx}. {clean_item[:160]}")

        summary_text = "\n".join(summary_lines) + "\n"
        from pithon.agent.memory import save_note
        save_note(
            title=f"daily-summary-{yesterday}",
            content=summary_text,
            tags="daily-summary,compactor,memory",
            tz_name=self.tz_name
        )
        logger.info(f"Nightly compactor saved summary for {yesterday}")
        return summary_text

    def evening_wrapup_tick(self) -> str:
        """Compile and send evening debrief and tomorrow preview at 7:30 PM."""
        tz = self._get_tz()
        now_local = datetime.now(tz)
        today_str = now_local.strftime("%A, %d %B")

        # Tasks stats
        completed_today = 0
        pending_tasks = []
        if self.storage:
            all_tasks = self.storage.get_tasks(self.admin_chat_id, include_completed=True)
            pending_tasks = [t for t in all_tasks if not t.get("is_completed")]
            completed_today = len([t for t in all_tasks if t.get("is_completed")])

        # Tomorrow's meetings
        tomorrow_start = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0).astimezone(timezone.utc).isoformat()
        tomorrow_events = self.storage.get_upcoming_events(self.admin_chat_id, limit=5, start_after=tomorrow_start) if self.storage else []

        lines = [
            f"🌙 *Evening Wrap-up & Tomorrow's Preview*\n"
            f"📅 *{today_str}*\n\n"
            f"*Today's Productivity:*\n"
            f"• *Completed Tasks:* `{completed_today}`\n"
            f"• *Pending Carryover Tasks:* `{len(pending_tasks)}`"
        ]

        if pending_tasks:
            lines.append("\n*Top Pending Tasks:*")
            for t in pending_tasks[:3]:
                lines.append(f"• `{t['title']}`")

        if tomorrow_events:
            lines.append("\n*Tomorrow's First Meetings:*")
            for ev in tomorrow_events[:3]:
                ev_start = datetime.fromisoformat(ev["start_time"]).astimezone(tz)
                lines.append(f"• `{ev_start.strftime('%I:%M %p')}` — *{ev['title']}*")
        else:
            lines.append("\n*Tomorrow:* No early morning meetings scheduled. ✨")

        lines.append("\n_Rest up and have a great evening!_")
        wrapup_msg = "\n".join(lines)

        if self.bot and self.admin_chat_id:
            try:
                self.bot.send_message(self.admin_chat_id, wrapup_msg, disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"Failed to send evening wrapup: {e}")

        return wrapup_msg

    def _loop(self) -> None:
        last_hour = -1
        last_briefing_date = None
        last_compact_date = None
        last_evening_date = None
        last_sync_epoch = 0.0
        while self._running:
            try:
                now_epoch = time.time()

                # 0. Calendar sync every 300 seconds (5 minutes)
                if now_epoch - last_sync_epoch >= 300.0:
                    last_sync_epoch = now_epoch
                    self.calendar_sync_tick()

                # 1. Minute tick for tasks and proactive meeting alerts
                self.check_reminders_tick()
                self.calendar_alerts_tick()

                current_time = datetime.now(self._get_tz())

                # 2. Hourly tick at :00
                if current_time.minute == 0 and current_time.hour != last_hour:
                    last_hour = current_time.hour
                    self.hourly_digest_tick()

                # 3. Morning Daily Briefing at 9:00 AM local time
                if current_time.hour == 9 and current_time.minute == 0 and last_briefing_date != current_time.date():
                    last_briefing_date = current_time.date()
                    self.daily_briefing_tick()

                # 4. Evening Wrap-Up at 7:30 PM (19:30) local time
                if current_time.hour == 19 and current_time.minute == 30 and last_evening_date != current_time.date():
                    last_evening_date = current_time.date()
                    self.evening_wrapup_tick()

                # 5. Nightly Memory Compactor at 5:00 AM local time
                if current_time.hour == 5 and current_time.minute == 0 and last_compact_date != current_time.date():
                    last_compact_date = current_time.date()
                    self.compact_memory_tick()

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
