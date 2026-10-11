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

logger = logging.getLogger("pithon.tools")

TOOLS_DEFINITIONS = [
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
    name = tool_call.get("name")
    args = tool_call.get("arguments", {})

    try:
        tz = zoneinfo.ZoneInfo(tz_name)
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
        msg = f"⏱️ *Timer set:* {label}\nAlert: `{due_clean} {tz_name}`"
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

        reply_markup = {
            "inline_keyboard": [
                [{"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"}]
            ]
        }
        list_tag = f" `[{list_name}]`" if list_name != "default" else ""
        msg = f"📌 Saved #{tid}: {title}{list_tag}"
        return msg, reply_markup, {"type": "task", "task_id": tid}

    elif name == "list_tasks":
        list_name = args.get("list_name")
        if storage:
            tasks = storage.get_tasks(str(chat_id), list_name=list_name)
            msg, inline_kb = format_tasks_message(tasks)
            reply_markup = {"inline_keyboard": inline_kb} if inline_kb else None
            return msg, reply_markup, {"type": "list_tasks", "count": len(tasks)}
        return "No storage.", None, None

    elif name == "calculate":
        expr = str(args.get("expression", "")).strip()
        res = safe_calculate(expr)
        msg = f"🧮 `{expr}` = *{res}*"
        return msg, None, {"type": "calculate", "expression": expr, "result": res}

    elif name == "get_weather":
        loc = str(args.get("location", "Bangalore")).strip()
        report = get_weather_report(loc)
        msg = report.get("summary", "No weather data.")
        return msg, None, {"type": "weather", "location": loc, "report": report}

    elif name == "save_note":
        title = str(args.get("title", "Note")).strip()
        content = str(args.get("content", "")).strip()
        res = save_note(title, content, tz_name=tz_name)
        action_verb = "Updated" if res.get("updated") else "Saved"
        msg = f"📝 *{action_verb} note:* `{res['filename']}`\n📌 *{title}*\n\n{content}"
        return msg, None, {"type": "note", "filename": res["filename"]}

    elif name == "search_notes":
        query = str(args.get("query", "")).strip()
        notes = search_notes(query)
        if not notes:
            all_n = list_notes()
            if not all_n:
                return f"No notes found matching '{query}'. Zero notes saved.", None, None
            titles = ", ".join(f"`{n['title']}`" for n in all_n[:5])
            return f"No match for '{query}'. Existing notes: {titles}", None, None

        lines = [f"🔍 *Found {len(notes)} note(s) for '{query}':*\n"]
        for n in notes[:3]:
            lines.append(f"• *{n['title']}* (`{n['filename']}`):\n{n['content'][:200]}...")
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

        reply_markup = {"inline_keyboard": [url_buttons]} if url_buttons else None
        context_block = format_search_context(results, query)
        return "", reply_markup, {"type": "search", "query": query, "results": results, "context": context_block}

    return f"Unknown tool: {name}", None, None
