import pytest
from datetime import datetime, timezone
from pithon.agent.tasks import (
    is_task_intent,
    parse_task_text,
    format_tasks_message,
    format_reminder_alert
)

def test_is_task_intent():
    assert is_task_intent("remind me to call mom at 5pm") is True
    assert is_task_intent("add milk to grocery list") is True
    assert is_task_intent("/add renew domain tomorrow") is True
    assert is_task_intent("remember to take medicine") is True
    assert is_task_intent("what is the capital of France?") is False
    assert is_task_intent("tell me a joke") is False

def test_parse_task_text():
    # Direct command parsing
    t1 = parse_task_text("/add Buy groceries tomorrow 5pm")
    assert "Buy groceries" in t1["title"]
    assert t1["list_name"] == "default"

    # With list specification
    t2 = parse_task_text("add bananas to list groceries")
    assert "bananas" in t2["title"]
    assert t2["list_name"] == "groceries"

    # Natural reminder
    t3 = parse_task_text("remind me to check server status in 3 hours")
    assert "check server status" in t3["title"]
    assert t3["due_at"] is not None

def test_format_tasks_message():
    tasks = [
        {"id": 1, "title": "Buy milk", "list_name": "groceries", "due_at": "2026-10-12T10:00:00", "is_completed": 0},
        {"id": 2, "title": "Call doctor", "list_name": "default", "due_at": None, "is_completed": 0}
    ]
    text, inline_keyboard = format_tasks_message(tasks)
    assert "📋 *Your Active Tasks*" in text
    assert "#1 Buy milk" in text
    assert "#2 Call doctor" in text
    assert len(inline_keyboard) == 2  # 2 rows of buttons
    assert inline_keyboard[0][0]["callback_data"] == "done:1"
    assert inline_keyboard[0][1]["callback_data"] == "snooze:1"
    assert inline_keyboard[0][2]["callback_data"] == "del:1"

def test_format_reminder_alert():
    task = {"id": 15, "title": "Weekly server backup", "due_at": "2026-10-11T16:00:00"}
    text, inline_keyboard = format_reminder_alert(task)
    assert "⏰ *Reminder Due Now!*" in text
    assert "Weekly server backup" in text
    assert inline_keyboard[0][0]["callback_data"] == "done:15"
