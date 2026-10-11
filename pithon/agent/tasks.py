"""Tasks, reminders, timers, and list management parser with interactive Telegram formatting."""

import re
from datetime import datetime, timedelta, timezone
import zoneinfo
from typing import Dict, Any, List, Optional, Tuple

TASK_INTENT_PATTERNS = [
    r"^/add\b",
    r"^/todo\b",
    r"^/tasks\b",
    r"^/timer\b",
    r"\btimer\b",
    r"\bremind\b",
    r"\bremember to\b",
    r"\badd\b.*\blist\b",
    r"\badd to (?:my )?todo\b",
    r"\bcreate (?:a )?task\b",
    r"\bset (?:a |an )?(?:timer|reminder|alarm)\b"
]

def is_task_intent(text: str) -> bool:
    """Check if the text represents an intention to manage or create tasks/timers."""
    clean = text.lower().strip()
    return any(re.search(pat, clean) for pat in TASK_INTENT_PATTERNS)

def parse_task_text(text: str, default_tz: str = "Asia/Kolkata") -> Dict[str, Any]:
    """Parse task/timer title, list name, and optional due date/time from text."""
    clean = text.strip()
    is_timer = bool(re.search(r"\btimer\b", clean, re.IGNORECASE) or clean.startswith("/timer"))
    list_name = "default"
    due_at = None

    # Check for list specification: e.g., "to list groceries" or "in list work"
    list_match = re.search(r"\b(?:to|in)\s+list\s+([a-zA-Z0-9_\-]+)", clean, re.IGNORECASE)
    if list_match:
        list_name = list_match.group(1).lower()
        clean = re.sub(r"\b(?:to|in)\s+list\s+[a-zA-Z0-9_\-]+", "", clean, flags=re.IGNORECASE).strip()

    total_seconds = 0
    # Match hours: e.g., "in 2 hours", "for 1 hr", "1h"
    h_m = re.search(r"(?:for|in|\b)\s*(\d+)\s*(?:hours?|hrs?|h)\b", clean, re.IGNORECASE)
    if h_m:
        total_seconds += int(h_m.group(1)) * 3600
        clean = re.sub(r"(?:for|in|\b)\s*" + h_m.group(1) + r"\s*(?:hours?|hrs?|h)\b", "", clean, flags=re.IGNORECASE)

    # Match minutes: e.g., "for 15 mins", "in 10 minutes", "15m"
    m_m = re.search(r"(?:for|in|\b)\s*(\d+)\s*(?:minutes?|mins?|m)\b", clean, re.IGNORECASE)
    if m_m:
        total_seconds += int(m_m.group(1)) * 60
        clean = re.sub(r"(?:for|in|\b)\s*" + m_m.group(1) + r"\s*(?:minutes?|mins?|m)\b", "", clean, flags=re.IGNORECASE)

    # Match seconds: e.g., "for 30 secs", "in 45 seconds", "30s"
    s_m = re.search(r"(?:for|in|\b)\s*(\d+)\s*(?:seconds?|secs?|s)\b", clean, re.IGNORECASE)
    if s_m:
        total_seconds += int(s_m.group(1))
        clean = re.sub(r"(?:for|in|\b)\s*" + s_m.group(1) + r"\s*(?:seconds?|secs?|s)\b", "", clean, flags=re.IGNORECASE)

    # Clean conversational prefixes and command markers
    title = clean
    title = re.sub(r"^(?:can you\s+)?(?:please\s+)?(?:set|start)\s+(?:a\s+|an\s+)?(?:timer|reminder|alarm)?(?:\s+for)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^/timer\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^/add\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^remind me\s+(?:to\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^remember\s+(?:to\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^add\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\btimer\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^(?:for|in)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[?!.]+$", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()

    try:
        tz = zoneinfo.ZoneInfo(default_tz)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)

    if total_seconds > 0:
        due_at = (now + timedelta(seconds=total_seconds)).isoformat()
    elif re.search(r"\btomorrow\b", text, re.IGNORECASE):
        due_at = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat()
        title = re.sub(r"\btomorrow\b", "", title, flags=re.IGNORECASE).strip()

    if is_timer and not title:
        mins = total_seconds // 60
        secs = total_seconds % 60
        if mins and secs:
            title = f"{mins}m {secs}s timer"
        elif mins:
            title = f"{mins}-minute timer"
        elif secs:
            title = f"{secs}-second timer"
        else:
            title = "Timer"

    if not title:
        title = "Untitled Task"

    return {
        "title": title,
        "list_name": list_name,
        "due_at": due_at,
        "is_timer": is_timer,
        "seconds": total_seconds
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

        row = [
            {"text": f"✅ Done #{tid}", "callback_data": f"done:{tid}"},
            {"text": "⏰ +1h", "callback_data": f"snooze:{tid}"},
            {"text": "🗑️ Del", "callback_data": f"del:{tid}"}
        ]
        inline_keyboard.append(row)

    return "\n".join(lines), inline_keyboard

def format_reminder_alert(task: Dict[str, Any]) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Format a scheduled reminder or timer alert for Telegram."""
    tid = task["id"]
    title = task["title"]
    is_timer = "timer" in title.lower()

    if is_timer:
        msg = (
            f"⏰ *TIMER UP!* 🔔\n\n"
            f"⏱️ Your *{title}* has finished!\n\n"
            f"Tap below to dismiss:"
        )
        inline_keyboard = [
            [
                {"text": "✅ Dismiss Timer", "callback_data": f"done:{tid}"}
            ]
        ]
    else:
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
