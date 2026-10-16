"""Native Qwen2.5 tool calling specifications and execution engine with Caveman Ultra compression."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Dict, Any, Optional, Tuple

from pithon.agent.calc import safe_calculate
from pithon.agent.weather import get_weather_report
from pithon.agent.memory import save_note, search_notes, list_notes
from pithon.agent.search import search_duckduckgo, format_search_context
from pithon.agent.tasks import format_tasks_message
from pithon.agent.markdown_escape import escape_markdown, escape_code

logger = logging.getLogger("pithon.tools")

TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get upcoming calendar meetings, schedule, and video call links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days ahead to look for meetings (default 1 for today)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Start countdown timer or alarm that alerts user after duration",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "integer", "description": "Count of units (e.g. 15, 30, 2)"},
                    "unit": {"type": "string", "enum": ["seconds", "minutes", "hours"], "description": "Time unit"},
                    "label": {"type": "string", "description": "Timer label"}
                },
                "required": ["duration", "unit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Save to-do task or reminder",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task description"},
                    "list_name": {"type": "string", "description": "List category (default, groceries, work)"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Show pending tasks or active to-do list",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_name": {"type": "string", "description": "Optional list category filter"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate exact mathematical expression or arithmetic without guessing",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression (e.g. (4320/6)*1.18, sqrt(144)+5)"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Fetch live weather report, temperature, and conditions for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or place name (e.g. Bangalore, London)"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save persistent note, password, or fact to markdown knowledge file",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title / subject"},
                    "content": {"type": "string", "description": "Note body / details to remember"}
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search saved markdown notes for facts, saved info, or memory",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or topic"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search live web via DuckDuckGo for breaking news, external facts, scores",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_briefing",
            "description": "Generate comprehensive daily briefing with weather, top 10 news (local, national, world), historical milestones, quote of the day, and tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Optional city name to override default location"}
                }
            }
        }
    }
]

def format_tools_system_prompt() -> str:
    """Format tools XML schema and Caveman Ultra style rules for Qwen2.5 system prompt."""
    tools_json = "\n".join(json.dumps(t) for t in TOOLS_DEFINITIONS)
    return (
        "# Mode: Caveman Ultra\n"
        "Respond terse like smart caveman. Drop articles (a, an, the), filler, pleasantries. "
        "One word when enough. State fact once. Numbers, code, facts: keep exact. No fluff.\n\n"
        "# Tools\n"
        "You have access to tools inside <tools></tools>:\n"
        "<tools>\n"
        f"{tools_json}\n"
        "</tools>\n\n"
        "When action or lookup needed, reply ONLY:\n"
        "<tool_call>\n"
        '{"name": <tool_name>, "arguments": <args_object>}\n'
        "</tool_call>\n"
        "Otherwise answer directly in caveman ultra."
    )

def extract_tool_call(model_output: str) -> Optional[Dict[str, Any]]:
    """Extract and parse tool call JSON from model output."""
    if not model_output:
        return None

    match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", model_output, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    try:
        data = json.loads(model_output.strip())
        if isinstance(data, dict) and "name" in data and "arguments" in data:
            return data
    except Exception:
        pass

    return None

def execute_tool_call(
    tool_call: Dict[str, Any],
    storage: Any,
    chat_id: str,
    tz_name: str = "Asia/Kolkata"
) -> Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Execute tool call.
    Returns: (reply_text, reply_markup, tool_context_dict)
    """
    raw_name = str(tool_call.get("name", "")).strip()
    args = tool_call.get("arguments", {})
    if not isinstance(args, dict):
        args = {}

    norm_name = re.sub(r"[^a-z0-9]", "", raw_name.lower())
    if norm_name in ("settimer", "timer"):
        name = "set_timer"
    elif norm_name in ("addtask", "task", "addtodo", "todo"):
        name = "add_task"
    elif norm_name in ("listtasks", "tasks", "gettasks", "todos"):
        name = "list_tasks"
    elif norm_name in ("getcalendarevents", "calendarevents", "calendar", "calender", "agenda", "getcalendar", "getagenda"):
        name = "get_calendar_events"
    elif norm_name in ("calculate", "calc", "math"):
        name = "calculate"
    elif norm_name in ("getweather", "weather"):
        name = "get_weather"
    elif norm_name in ("savenote", "note", "addnote"):
        name = "save_note"
    elif norm_name in ("searchnotes", "findnotes", "notes"):
        name = "search_notes"
    elif norm_name in ("websearch", "search", "duckduckgo"):
        name = "web_search"
    elif norm_name in ("getdailybriefing", "briefing", "dailybriefing"):
        name = "get_daily_briefing"
    else:
        name = raw_name

    try:
        tz: Any = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)

    if name == "set_timer":
        duration = int(args.get("duration", 0))
        unit = str(args.get("unit", "minutes")).lower()
        label = str(args.get("label", "")).strip() or f"{duration}-{unit} timer"

        multiplier = 60
        if "hour" in unit:
            multiplier = 3600
        elif "sec" in unit:
            multiplier = 1

        total_secs = duration * multiplier
        due_at = (now + timedelta(seconds=total_secs)).isoformat()
        due_clean = due_at[:19].replace("T", " ")

        tid = 0
        if storage:
            tid = storage.create_task(
                chat_id=chat_id,
                title=label,
                list_name="timer",
                due_at=due_at
            )

        reply_markup = {
            "inline_keyboard": [
                [{"text": "❌ Cancel Timer", "callback_data": f"del:{tid}"}]
            ]
        }
        msg = f"⏱️ *Timer set:* {escape_markdown(label)}\nAlert: `{due_clean} {tz_name}`"
        return msg, reply_markup, {"type": "timer", "task_id": tid, "seconds": total_secs}

    elif name == "add_task":
        title = str(args.get("title", "Task")).strip()
        list_name = str(args.get("list_name", "default")).strip()

        tid = 0
        if storage:
            tid = storage.create_task(
                chat_id=chat_id,
                title=title,
                list_name=list_name
            )

        task_markup: Optional[Dict[str, Any]] = {
            "inline_keyboard": [
                [{"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"}]
            ]
        }
        list_tag = f" `[{list_name}]`" if list_name != "default" else ""
        msg = f"📌 Saved #{tid}: {escape_markdown(title)}{list_tag}"
        return msg, task_markup, {"type": "task", "task_id": tid}

    elif name == "list_tasks":
        target_list = str(args["list_name"]) if args.get("list_name") is not None else None
        if storage:
            tasks = storage.get_tasks(str(chat_id), list_name=target_list)
            msg, inline_kb = format_tasks_message(tasks)
            task_list_markup: Optional[Dict[str, Any]] = {"inline_keyboard": inline_kb} if inline_kb else None
            return msg, task_list_markup, {"type": "list_tasks", "count": len(tasks)}
        return "No storage.", None, None

    elif name == "calculate":
        expr = str(args.get("expression", "")).strip()
        res = safe_calculate(expr)
        msg = f"🧮 `{escape_code(expr)}` = *{res}*"
        return msg, None, {"type": "calculate", "expression": expr, "result": res}

    elif name == "get_weather":
        loc = str(args.get("location", "Bangalore")).strip()
        report = get_weather_report(loc)
        msg = report.get("summary", "No weather data.")
        return msg, None, {"type": "weather", "location": loc, "report": report}

    elif name == "save_note":
        title = str(args.get("title", "Note")).strip()
        content = str(args.get("content", "")).strip()
        note_res = save_note(title, content, tz_name=tz_name, base_dir=(storage.notes_dir() if storage else None))
        action_verb = "Updated" if note_res.get("updated") else "Saved"
        msg = (
            f"📝 *{action_verb} note:* `{note_res['filename']}`\n"
            f"📌 *{escape_markdown(title)}*\n\n{escape_markdown(content)}"
        )
        return msg, None, {"type": "note", "filename": note_res["filename"]}

    elif name == "search_notes":
        query = str(args.get("query", "")).strip()
        notes = search_notes(query, base_dir=(storage.notes_dir() if storage else None))
        if not notes:
            all_n = list_notes(base_dir=(storage.notes_dir() if storage else None))
            if not all_n:
                return f"No notes found matching '{escape_markdown(query)}'. Zero notes saved.", None, None
            titles = ", ".join(f"`{n['title']}`" for n in all_n[:5])
            return f"No match for '{escape_markdown(query)}'. Existing notes: {titles}", None, None

        lines = [f"🔍 *Found {len(notes)} note(s) for '{escape_markdown(query)}':*\n"]
        for n in notes[:3]:
            lines.append(
                f"• *{escape_markdown(n['title'])}* (`{n['filename']}`):"
                f"\n{escape_markdown(n['content'][:200])}..."
            )
        msg = "\n\n".join(lines)
        return msg, None, {"type": "search_notes", "query": query, "results": notes}

    elif name == "web_search":
        query = str(args.get("query", "")).strip()
        results = search_duckduckgo(query, max_results=3)

        url_buttons = []
        for r in results:
            if r.get("url"):
                import urllib.parse
                domain = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                url_buttons.append({"text": f"🌐 {domain[:18]}", "url": r["url"]})

        search_markup: Optional[Dict[str, Any]] = {"inline_keyboard": [url_buttons]} if url_buttons else None
        context_block = format_search_context(results, query)
        return "", search_markup, {"type": "search", "query": query, "results": results, "context": context_block}

    elif name == "get_calendar_events":
        if not storage:
            return "No storage available to retrieve calendar.", None, {"type": "calendar"}
        days = int(args.get("days", 1)) if isinstance(args, dict) else 1
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = today_midnight.astimezone(zoneinfo.ZoneInfo("UTC")).isoformat()
        events = storage.get_upcoming_events(chat_id, limit=15, start_after=start_utc)
        if not events and chat_id != "web":
            events = storage.get_upcoming_events("web", limit=15, start_after=start_utc)

        max_dt = today_midnight + timedelta(days=days, hours=23, minutes=59)
        matching = []
        for ev in events:
            try:
                ev_start = datetime.fromisoformat(ev["start_time"]).astimezone(tz)
                if ev_start <= max_dt:
                    matching.append((ev_start, ev))
            except Exception:
                continue

        if not matching:
            period = "today" if days == 1 else f"the next {days} days"
            return f"📅 No meetings scheduled for {period} ✨", None, {"type": "calendar"}

        lines = [f"📅 *Upcoming Meetings ({len(matching)} found):*"]
        for ev_start, ev in matching:
            ev_end = datetime.fromisoformat(ev["end_time"]).astimezone(tz)
            date_prefix = f"{ev_start.strftime('%a %d %b')} " if days > 1 else ""
            t_str = f"{date_prefix}{ev_start.strftime('%I:%M %p')} - {ev_end.strftime('%I:%M %p')}"
            link = ev.get("meeting_link")
            ev_title = escape_markdown(ev["title"])
            loc = f" _({escape_markdown(ev['location'])})_" if ev.get("location") else ""
            if link:
                lines.append(f"• `{t_str}` — [{ev_title}]({link}){loc}")
            else:
                lines.append(f"• `{t_str}` — *{ev_title}*{loc}")

        return "\n".join(lines), None, {"type": "calendar"}

    elif name == "get_daily_briefing":
        from pithon.agent.briefing import generate_daily_briefing
        override_city = args.get("city")
        briefing = generate_daily_briefing(chat_id=chat_id, storage=storage, tz_name=tz_name, override_city=override_city)
        return briefing, None, {"type": "briefing"}

    return f"Unknown tool: {name}", None, None
