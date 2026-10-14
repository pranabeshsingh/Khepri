"""Deterministic intent router fast-pathing common queries without LLM token generation."""

import re
import zoneinfo
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from pithon.agent.calc import safe_calculate
from pithon.agent.calendar import is_calendar_intent
from pithon.agent.weather import is_weather_intent, extract_weather_location, get_weather_report
from pithon.agent.time_context import get_current_time_info
from pithon.agent.memory import search_notes
from pithon.agent.tasks import is_task_intent, parse_task_text
from pithon.agent.tools import execute_tool_call


def is_time_intent(text: str) -> bool:
    """Check if query is asking for current time or date."""
    clean = text.lower().strip()
    patterns = [
        r"\b(?:what time is it|current time|what's the time|tell me the time|time now)\b",
        r"\b(?:what day is today|what is today's date|today's date|what date is it)\b",
        r"^/time\b",
        r"^time\b"
    ]
    return any(re.search(p, clean) for p in patterns)


def is_status_intent(text: str) -> bool:
    """Check if query is asking about system health or status."""
    clean = text.lower().strip()
    patterns = [
        r"\b(?:system status|health status|bot status|server status|system health|uptime)\b",
        r"^/status\b"
    ]
    return any(re.search(p, clean) for p in patterns)


def is_notes_search_intent(text: str) -> Optional[str]:
    """Check if query is searching for notes and return the search term."""
    clean = text.strip()
    m = re.search(r"\b(?:search|find|show)\s+(?:my\s+)?notes?\s+(?:for|on|about)?\s*(.+)$", clean, re.IGNORECASE)
    if m:
        query = m.group(1).strip()
        if len(query) > 1:
            return query
    if clean.lower().startswith(("/search ", "/find ")):
        parts = clean.split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip()
    return None


def is_math_intent(text: str) -> Optional[str]:
    """Check if query is a pure math calculation expression."""
    clean = text.strip()
    # Check for prefix like /calc or 'what is'
    m_calc = re.match(r"^/calc\s+(.+)$", clean, re.IGNORECASE)
    if m_calc:
        return m_calc.group(1).strip()

    m_what = re.match(r"^(?:what is|calc|calculate)\s+([0-9\s\+\-\*\/\^\(\)\.\%]+)$", clean, re.IGNORECASE)
    if m_what:
        expr = m_what.group(1).strip()
        if re.search(r"[\+\-\*\/\^]", expr):
            return expr

    # Pure arithmetic expression: e.g. "450 * 1.18 + 32"
    if re.match(r"^[0-9\s\+\-\*\/\^\(\)\.\%]+$", clean) and re.search(r"[\+\-\*\/\^]", clean):
        return clean

    return None


def route_fast_path(
    text: str,
    storage: Any,
    chat_id: str,
    tz_name: str = "Asia/Kolkata",
    admin_chat_id: str = ""
) -> Optional[Tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]]:
    """Evaluate message against deterministic rule-based intents.

    Returns:
        (reply_text, reply_markup, tool_context_dict) if fast-path matched,
        or None if message should fall through to the LLM.
    """
    clean = text.strip()
    if not clean:
        return None

    # 1. Calendar / Agenda Intent
    if is_calendar_intent(clean) or clean.startswith(("/calendar", "/calender", "/agenda")):
        days = 2 if "tomorrow" in clean.lower() else 1
        reply_text, reply_markup, ctx = execute_tool_call(
            {"name": "get_calendar_events", "arguments": {"days": days}},
            storage,
            str(chat_id),
            tz_name
        )
        return reply_text, reply_markup, ctx

    # 2. Time & Date Intent
    if is_time_intent(clean):
        info = get_current_time_info(tz_name)
        time_msg = (
            f"🕒 *Current Date & Time*\n\n"
            f"• *Date:* {info['weekday']}, {info['day']} {info['month']} {info['year']}\n"
            f"• *Time:* {info['time']} ({info['time_12h']})\n"
            f"• *Timezone:* `{info['timezone']}` (UTC{info['utc_offset'][:3]}:{info['utc_offset'][3:]})"
        )
        return time_msg, None, {"type": "time"}

    # 3. Weather Intent
    if is_weather_intent(clean) or clean.startswith("/weather"):
        default_city = "Kolkata"
        if storage:
            prof = storage.get_user_profile(str(chat_id)) or {}
            default_city = prof.get("city") or "Kolkata"

        loc = extract_weather_location(clean, default_loc=default_city)
        res = get_weather_report(loc)
        return res.get("summary", "Weather unavailable."), None, {"type": "weather", "location": loc}

    # 4. Math / Calculation Intent
    expr = is_math_intent(clean)
    if expr:
        res = safe_calculate(expr)
        reply = f"🧮 *Result:*\n`{expr}` = `{res}`"
        return reply, None, {"type": "calc", "expression": expr, "result": res}

    # 5. Notes Search Intent
    search_q = is_notes_search_intent(clean)
    if search_q:
        results = search_notes(search_q)
        if not results:
            reply = f"📝 No saved notes matching *'{search_q}'*."
        else:
            lines = [f"📝 *Saved Notes Matching '{search_q}':*\n"]
            for r in results[:5]:
                lines.append(f"• *{r['title']}* (`{r['filename']}`)\n  {r['content'][:140]}...")
            reply = "\n".join(lines)
        return reply, None, {"type": "notes", "query": search_q}

    # 6. System Status Intent
    if is_status_intent(clean):
        info = get_current_time_info(tz_name)
        active_tasks = len(storage.get_tasks(str(chat_id))) if storage else 0
        status_msg = (
            f"🛡️ *Khepri System Health*\n\n"
            f"• *Daemon Status:* Healthy (loopback)\n"
            f"• *Memory Bound:* 4GB Pi 4 Architecture (strict cgroups)\n"
            f"• *Active Tasks:* {active_tasks}\n"
            f"• *Local Time:* `{info['time']}` ({tz_name})\n"
            f"• *Uptime:* Continuous autonomous agent"
        )
        return status_msg, None, {"type": "status"}

    # 7. Explicit Task / Timer Slash Commands
    if clean.startswith(("/add", "/timer", "/todo")):
        task_info = parse_task_text(clean, default_tz=tz_name)
        if storage and (task_info.get("seconds", 0) > 0 or task_info.get("due_at")):
            list_name = "timer" if task_info.get("is_timer") else task_info["list_name"]
            tid = storage.create_task(
                str(chat_id),
                task_info["title"],
                list_name=list_name,
                due_at=task_info["due_at"]
            )
            due_clean = task_info["due_at"][:19].replace("T", " ") if task_info.get("due_at") else ""
            if task_info.get("is_timer"):
                secs = task_info.get("seconds", 0)
                dur = f"{secs // 60}m" if secs >= 60 else f"{secs}s"
                reply = f"⏱️ *Timer set:* '{task_info['title']}' for *{dur}* (Alert at `{due_clean}`)."
                reply_markup = {"inline_keyboard": [[{"text": "❌ Cancel Timer", "callback_data": f"del:{tid}"}]]}
            else:
                reply = f"📋 *Task created:* '{task_info['title']}' (Due: `{due_clean}`)."
                reply_markup = {"inline_keyboard": [[{"text": "✅ Done", "callback_data": f"done:{tid}"}]]}
            return reply, reply_markup, {"type": "task", "id": tid}

    return None
