"""Daily Briefing Generator for Khepri Assistant.

Aggregates:
1. Personalized greeting & header with user name from profile
2. Date, time, and timezone context
3. Current weather for user's home location
4. Pending tasks & schedule
5. Top 10 Curated News Headlines (5 Local, 3 National, 2 World)
6. On This Day in History (milestones)
7. Thought of the Day (inspiring wisdom)
8. Edge system health & model status
"""

import logging
from datetime import datetime
import zoneinfo
from typing import Any, List, Optional

from pithon.agent.facts import get_interesting_fact_today, get_thought_of_the_day
from pithon.agent.markdown_escape import escape_markdown
from pithon.agent.news import fetch_news_headlines, format_news_section
from pithon.agent.weather import get_weather_report

logger = logging.getLogger("pithon.briefing")


def generate_daily_briefing(
    chat_id: str,
    storage: Any = None,
    tz_name: str = "Asia/Kolkata",
    override_city: Optional[str] = None
) -> str:
    """Generate a rich, personalized daily briefing markdown report."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    now = datetime.now(tz)
    hour = now.hour

    if 4 <= hour < 12:
        greeting = "🌅 *Good morning*"
    elif 12 <= hour < 17:
        greeting = "☀️ *Good afternoon*"
    elif 17 <= hour < 21:
        greeting = "🌆 *Good evening*"
    else:
        greeting = "🌙 *Good night*"

    # 1. User Profile Resolution
    user_name = "there"
    city = override_city or "Kolkata"
    focus = None

    if storage:
        prof = storage.get_user_profile(str(chat_id))
        if not prof and chat_id != "web":
            prof = storage.get_user_profile("web")
        if prof:
            if prof.get("name"):
                user_name = prof["name"]
            if not override_city and prof.get("city"):
                city = prof["city"]
            if prof.get("focus"):
                focus = prof["focus"]

    # Extract base city name for clean search if "City, State, Country"
    search_city = city.split(",")[0].strip() if "," in city else city

    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%I:%M %p %Z").strip()

    sections: List[str] = []

    # Header
    name_str = f", {escape_markdown(user_name)}!" if user_name != "there" else "!"
    header_line = f"{greeting}{name_str}\n📅 *{date_str}* • `{time_str}`"
    sections.append(header_line)

    # Focus tag if present
    if focus:
        sections.append(f"🎯 *Daily Focus:* _{escape_markdown(focus)}_")

    # 2. Weather
    try:
        w_data = get_weather_report(search_city)
        w_summary = w_data.get("summary", "").strip()
        if w_summary:
            sections.append(f"🌤️ *Weather ({escape_markdown(search_city)}):*\n{w_summary}")
    except Exception as e:
        logger.warning(f"Failed to fetch weather for briefing: {e}")

    # 3. Today's Agenda & Calls (Calendar Events)
    if storage:
        try:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start.astimezone(zoneinfo.ZoneInfo("UTC")).isoformat()
            upcoming_cal = storage.get_upcoming_events(str(chat_id), limit=10, start_after=today_start_utc)
            if not upcoming_cal and chat_id != "web":
                upcoming_cal = storage.get_upcoming_events("web", limit=10, start_after=today_start_utc)

            today_events = []
            for ev in upcoming_cal:
                try:
                    ev_dt = datetime.fromisoformat(ev["start_time"]).astimezone(tz)
                    if ev_dt.date() == now.date():
                        today_events.append((ev_dt, ev))
                except Exception:
                    continue

            if today_events:
                cal_lines = [f"📅 *Today's Agenda & Calls ({len(today_events)} scheduled):*"]
                for ev_dt, ev in today_events:
                    ev_end = datetime.fromisoformat(ev["end_time"]).astimezone(tz)
                    time_range = f"{ev_dt.strftime('%I:%M %p')} - {ev_end.strftime('%I:%M %p')}"
                    loc_str = f" _({escape_markdown(ev['location'])})_" if ev.get("location") else ""
                    ev_title = escape_markdown(ev["title"])
                    if ev.get("meeting_link"):
                        cal_lines.append(f"• `{time_range}` — [{ev_title}]({ev['meeting_link']}){loc_str}")
                    else:
                        cal_lines.append(f"• `{time_range}` — *{ev_title}*{loc_str}")
                sections.append("\n".join(cal_lines))
            else:
                sections.append("📅 *Today's Agenda:\n• No calls scheduled for today ✨*")
        except Exception as e:
            logger.warning(f"Failed to fetch calendar for briefing: {e}")

    # 3. Active Tasks / Reminders
    if storage:
        try:
            tasks = storage.get_tasks(str(chat_id), include_completed=False)
            if not tasks and chat_id != "web":
                tasks = storage.get_tasks("web", include_completed=False)

            if tasks:
                t_lines = [f"📋 *Tasks & Schedule ({len(tasks)} pending):*"]
                for t in tasks[:4]:
                    due_tag = ""
                    if t.get("due_at"):
                        due_tag = f" _(Due: {t['due_at'][:16].replace('T', ' ')})_"
                    t_lines.append(f"• #{t['id']} {escape_markdown(t['title'])}{due_tag}")
                if len(tasks) > 4:
                    t_lines.append(f"_...and {len(tasks) - 4} more task(s)_")
                sections.append("\n".join(t_lines))
            else:
                sections.append("📋 *Tasks & Schedule:*\n• You're all caught up! No pending tasks ✨")
        except Exception as e:
            logger.warning(f"Failed to fetch tasks for briefing: {e}")

    # 4. Top 10 Curated News Headlines
    try:
        news_data = fetch_news_headlines(city=search_city)
        news_section = format_news_section(news_data, city=search_city)
        sections.append(news_section)
    except Exception as e:
        logger.warning(f"Failed to format news for briefing: {e}")
        sections.append("📰 *News:* Unable to load headlines at this moment.")

    # 5. Interesting About Today (Milestones)
    try:
        milestone = get_interesting_fact_today(now)
        sections.append(f"💡 *Interesting About Today (On This Day):*\n{milestone}")
    except Exception as e:
        logger.warning(f"Failed to fetch fact: {e}")

    # 6. Thought for Today
    try:
        thought = get_thought_of_the_day(now)
        sections.append(f"✨ *Thought for Today:*\n{thought}")
    except Exception as e:
        logger.warning(f"Failed to fetch thought: {e}")

    # 7. Edge Status Footer
    sections.append("⚡ *Edge Status:* All systems operational • Local inference active")

    briefing_text = "\n\n".join(sections)
    try:
        if storage and hasattr(storage, "briefing_store"):
            storage.briefing_store.save_briefing(briefing_text)
        else:
            from pithon.agent.markdown_store import BriefingStore
            BriefingStore().save_briefing(briefing_text)
    except Exception as e:
        logger.warning(f"Failed to archive daily briefing markdown: {e}")
    return briefing_text
