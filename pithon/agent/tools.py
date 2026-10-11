"""Native Qwen2.5 tool calling specifications and execution engine."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Dict, Any, List, Optional, Tuple

from pithon.agent.search import search_duckduckgo, format_search_context

logger = logging.getLogger("pithon.tools")

TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a countdown timer or alarm that will alert the user after a specified duration",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "integer", "description": "Number of time units (e.g. 15, 30, 2)"},
                    "unit": {"type": "string", "enum": ["seconds", "minutes", "hours"], "description": "Unit of time"},
                    "label": {"type": "string", "description": "Optional label or description of what the timer is for"}
                },
                "required": ["duration", "unit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Create a task, reminder, or to-do list item",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Description of the task or item"},
                    "list_name": {"type": "string", "description": "Name of the list (e.g. default, groceries, work)"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live web via DuckDuckGo for current news, facts, scores, prices, or weather",
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
    """Format tools XML schema for Qwen2.5 system prompt."""
    tools_json = "\n".join(json.dumps(t) for t in TOOLS_DEFINITIONS)
    return (
        "# Tools\n\n"
        "You are provided with function signatures within <tools></tools> XML tags:\n"
        "<tools>\n"
        f"{tools_json}\n"
        "</tools>\n\n"
        "If you need to call a tool to fulfill the user's request, return ONLY:\n"
        "<tool_call>\n"
        '{"name": <function-name>, "arguments": <args-json-object>}\n'
        "</tool_call>\n"
        "Otherwise, answer directly."
    )

def extract_tool_call(model_output: str) -> Optional[Dict[str, Any]]:
    """Extract and parse tool call JSON from model output."""
    if not model_output:
        return None

    # Check for <tool_call> XML tags
    match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", model_output, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    # Fallback: check if the whole response is a valid tool call JSON
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
        unit = args.get("unit", "minutes").lower()
        label = args.get("label", "").strip() or f"{duration}-{unit} timer"

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
        msg = (
            f"⏱️ *Timer Started!*\n\n"
            f"📌 *Timer:* {label}\n"
            f"🕒 *Alert at:* `{due_clean} {tz_name}`\n\n"
            f"_I will alert you as soon as time is up!_"
        )
        return msg, reply_markup, {"type": "timer", "task_id": tid, "seconds": total_secs}

    elif name == "add_task":
        title = args.get("title", "Untitled Task").strip()
        list_name = args.get("list_name", "default").strip()

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
        msg = f"📌 Saved task *#{tid}*: {title}{list_tag}"
        return msg, reply_markup, {"type": "task", "task_id": tid}

    elif name == "web_search":
        query = args.get("query", "").strip()
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
