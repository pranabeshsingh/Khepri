"""Tasks, reminders, and list management parser with interactive Telegram formatting."""

import re
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Dict, Any, List, Optional, Tuple

TASK_INTENT_PATTERNS = [
    r"^/add\b",
    r"^/todo\b",
    r"^/tasks\b",
    r"\bremind me\b",
    r"\bremember to\b",
    r"\badd\b.*\blist\b",
    r"\badd to (?:my )?todo\b",
    r"\bcreate (?:a )?task\b"
]

def is_task_intent(text: str) -> bool:
    """Check if the text represents an intention to manage or create tasks."""
    clean = text.lower().strip()
    return any(re.search(pat, clean) for pat in TASK_INTENT_PATTERNS)

def parse_task_text(text: str, default_tz: str = "Asia/Kolkata") -> Dict[str, Any]:
    """Parse task title, list name, and optional due date/time from text."""
    clean = text.strip()
    list_name = "default"
    due_at = None

    # Check for list specification: e.g., "to list groceries" or "in list work"
    list_match = re.search(r"\b(?:to|in)\s+list\s+([a-zA-Z0-9_\-]+)", clean, re.IGNORECASE)
    if list_match:
        list_name = list_match.group(1).lower()
        clean = re.sub(r"\b(?:to|in)\s+list\s+[a-zA-Z0-9_\-]+", "", clean, flags=re.IGNORECASE).strip()

    # Strip prefixes: /add, remind me to, remember to, add
    title = clean
    title = re.sub(r"^/add\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^remind me\s+(?:to\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^remember\s+(?:to\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^add\s+", "", title, flags=re.IGNORECASE)

    # Simple relative duration extraction: "in X hours", "in X minutes"
    try:
        tz = zoneinfo.ZoneInfo(default_tz)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)

    rel_hours = re.search(r"\bin\s+(\d+)\s+hours?\b", title, re.IGNORECASE)
    if rel_hours:
        hrs = int(rel_hours.group(1))
        due_at = (now + timedelta(hours=hrs)).isoformat()
        title = re.sub(r"\bin\s+\d+\s+hours?\b", "", title, flags=re.IGNORECASE).strip()

    rel_mins = re.search(r"\bin\s+(\d+)\s+minutes?\b", title, re.IGNORECASE)
    if not due_at and rel_mins:
        mins = int(rel_mins.group(1))
        due_at = (now + timedelta(minutes=mins)).isoformat()
        title = re.sub(r"\bin\s+\d+\s+minutes?\b", "", title, flags=re.IGNORECASE).strip()

    if not due_at and re.search(r"\btomorrow\b", title, re.IGNORECASE):
        due_at = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat()
        title = re.sub(r"\btomorrow\b", "", title, flags=re.IGNORECASE).strip()

    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        title = "Untitled Task"

    return {
        "title": title,
        "list_name": list_name,
        "due_at": due_at
    }

def format_tasks_message(tasks: List[Dict[str, Any]]) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Format active tasks for Telegram with interactive callback buttons."""
    if not tasks:
        return "✨ You have no pending tasks! Enjoy your day.", []

    lines = ["📋 *Your Active Tasks*:\n"]
    inline_keyboard = []

    for t in tasks:
        tid = t["id"]
        title = t["title"]
        due_str = ""
        if t.get("due_at"):
            due_clean = t["due_at"][:16].replace("T", " ")
            due_str = f" _(Due: {due_clean})_"

        list_tag = f" `[{t['list_name']}]`" if t.get("list_name") and t["list_name"] != "default" else ""
        lines.append(f"• #{tid} {title}{list_tag}{due_str}")

        # Row of interactive buttons for this task
        row = [
            {"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"},
            {"text": "⏰ +1h", "callback_data": f"snooze:{tid}"},
            {"text": "🗑️ Del", "callback_data": f"del:{tid}"}
        ]
        inline_keyboard.append(row)

    return "\n".join(lines), inline_keyboard

def format_reminder_alert(task: Dict[str, Any]) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Format a scheduled reminder alert for Telegram."""
    tid = task["id"]
    title = task["title"]
    due_clean = task.get("due_at", "")[:16].replace("T", " ")

    msg = (
        f"⏰ *Reminder Due Now!*\n\n"
        f"📌 *Task:* {title}\n"
        f"🕒 *Scheduled:* {due_clean}\n\n"
        f"Click below to mark completed or snooze:"
    )

    inline_keyboard = [
        [
            {"text": f"✅ Mark Completed", "callback_data": f"done:{tid}"},
            {"text": "⏰ Snooze 1 Hour", "callback_data": f"snooze:{tid}"}
        ]
    ]

    return msg, inline_keyboard
