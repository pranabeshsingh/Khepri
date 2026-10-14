from datetime import datetime, timedelta
import zoneinfo
import pytest
from pithon.agent.tools import (
    format_tools_system_prompt,
    extract_tool_call,
    execute_tool_call,
    TOOLS_DEFINITIONS
)
from pithon.agent.storage import Storage

def test_format_tools_system_prompt():
    prompt = format_tools_system_prompt()
    assert "<tools>" in prompt
    assert "</tools>" in prompt
    assert "set_timer" in prompt
    assert "add_task" in prompt
    assert "web_search" in prompt
    assert "<tool_call>" in prompt

def test_extract_tool_call_xml():
    output = """Here is your timer:
<tool_call>
{"name": "set_timer", "arguments": {"duration": 15, "unit": "minutes", "label": "pasta"}}
</tool_call>"""
    extracted = extract_tool_call(output)
    assert extracted is not None
    assert extracted["name"] == "set_timer"
    assert extracted["arguments"]["duration"] == 15
    assert extracted["arguments"]["unit"] == "minutes"
    assert extracted["arguments"]["label"] == "pasta"

def test_extract_tool_call_json_fallback():
    output = '{"name": "add_task", "arguments": {"title": "buy milk"}}'
    extracted = extract_tool_call(output)
    assert extracted is not None
    assert extracted["name"] == "add_task"
    assert extracted["arguments"]["title"] == "buy milk"

def test_extract_tool_call_none():
    output = "Hello! I am a helpful AI assistant."
    assert extract_tool_call(output) is None

def test_execute_tool_call_set_timer(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = Storage(db_file)
    tool_call = {
        "name": "set_timer",
        "arguments": {"duration": 15, "unit": "minutes", "label": "tea"}
    }
    reply, markup, ctx = execute_tool_call(tool_call, storage, "12345")
    assert "Timer set:" in reply
    assert "tea" in reply
    assert markup is not None
    assert len(markup["inline_keyboard"]) == 1
    assert "del:" in markup["inline_keyboard"][0][0]["callback_data"]
    assert ctx["type"] == "timer"
    assert ctx["seconds"] == 900

    tasks = storage.get_tasks("12345")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "tea"
    assert tasks[0]["list_name"] == "timer"

def test_execute_tool_call_add_task(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = Storage(db_file)
    tool_call = {
        "name": "add_task",
        "arguments": {"title": "buy apples", "list_name": "groceries"}
    }
    reply, markup, ctx = execute_tool_call(tool_call, storage, "12345")
    assert "buy apples" in reply
    assert "[groceries]" in reply
    assert markup is not None
    assert "done:" in markup["inline_keyboard"][0][0]["callback_data"]

    tasks = storage.get_tasks("12345")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "buy apples"
    assert tasks[0]["list_name"] == "groceries"

def test_execute_tool_call_web_search(monkeypatch):
    import pithon.agent.tools
    monkeypatch.setattr(
        pithon.agent.tools,
        "search_duckduckgo",
        lambda query, max_results=3: [{"title": "Example", "snippet": "Test snippet", "url": "https://example.com"}]
    )
    tool_call = {
        "name": "web_search",
        "arguments": {"query": "test query"}
    }
    reply, markup, ctx = execute_tool_call(tool_call, None, "12345")
    assert ctx["type"] == "search"
    assert ctx["query"] == "test query"
    assert markup is not None
    assert markup["inline_keyboard"][0][0]["url"] == "https://example.com"

def test_caveman_ultra_prompt():
    prompt = format_tools_system_prompt()
    assert "Caveman Ultra" in prompt
    assert "Drop articles" in prompt
    assert "calculate" in prompt
    assert "get_weather" in prompt
    assert "save_note" in prompt
    assert "search_notes" in prompt
    assert "list_tasks" in prompt

def test_execute_tool_call_calculate():
    tool_call = {
        "name": "calculate",
        "arguments": {"expression": "(4320 / 6) * 1.18"}
    }
    reply, markup, ctx = execute_tool_call(tool_call, None, "12345")
    assert "849.6" in reply
    assert ctx["result"] == "849.6"

def test_execute_tool_call_weather(monkeypatch):
    import pithon.agent.tools
    monkeypatch.setattr(
        pithon.agent.tools,
        "get_weather_report",
        lambda loc: {"success": True, "location": "Bangalore", "summary": "🌤️ Weather for Bangalore: 28C"}
    )
    tool_call = {
        "name": "get_weather",
        "arguments": {"location": "Bangalore"}
    }
    reply, markup, ctx = execute_tool_call(tool_call, None, "12345")
    assert "Bangalore" in reply
    assert "28C" in reply

def test_execute_tool_call_save_and_search_notes(tmp_path, monkeypatch):
    notes_dir = str(tmp_path / "notes")
    monkeypatch.setenv("NOTES_DIR", notes_dir)

    tool_save = {
        "name": "save_note",
        "arguments": {"title": "Locker Code", "content": "9876 master"}
    }
    reply, markup, ctx = execute_tool_call(tool_save, None, "12345")
    assert "Saved note" in reply
    assert "locker-code.md" in reply

    tool_search = {
        "name": "search_notes",
        "arguments": {"query": "locker"}
    }
    reply_s, _, ctx_s = execute_tool_call(tool_search, None, "12345")
    assert "Locker Code" in reply_s
    assert "9876 master" in reply_s

def test_execute_tool_call_list_tasks(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = Storage(db_file)
    storage.create_task("12345", "Buy groceries", list_name="food")
    storage.create_task("12345", "Fix bike", list_name="errands")

    tool_call = {
        "name": "list_tasks",
        "arguments": {}
    }
    reply, markup, ctx = execute_tool_call(tool_call, storage, "12345")
    assert "Buy groceries" in reply
    assert "Fix bike" in reply
    assert markup is not None
    assert len(markup["inline_keyboard"]) == 2


def test_get_calendar_events_tool(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = Storage(db_file)
    storage.save_user_profile("user_1", name="Pranabesh")
    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=3)).isoformat()
    storage.save_calendar_events("user_1", [{
        "id": "e-1",
        "parent_uid": "e-1",
        "title": "Daily Sync",
        "description": "",
        "location": "Meet",
        "meeting_link": "https://meet.google.com/xyz",
        "start_time": start_time,
        "end_time": end_time,
        "is_recurring": 0,
        "event_md5": "md5"
    }])
    tool_call = {"name": "get_calendar_events", "arguments": {"days": 1}}
    reply, markup, ctx = execute_tool_call(tool_call, storage, "user_1", tz_name="Asia/Kolkata")
    assert "Daily Sync" in reply
    assert ctx["type"] == "calendar"


def test_execute_tool_call_normalized_names(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = Storage(db_file)
    storage.save_user_profile("user_1", name="Pranabesh")
    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=3)).isoformat()
    storage.save_calendar_events("user_1", [{
        "id": "e-1",
        "parent_uid": "e-1",
        "title": "Daily Scrum",
        "description": "",
        "location": "Teams",
        "meeting_link": "https://teams.microsoft.com/xyz",
        "start_time": start_time,
        "end_time": end_time,
        "is_recurring": 0,
        "event_md5": "md5"
    }])
    # Test un-underscored Qwen output: getcalendarevents
    call1 = {"name": "getcalendarevents", "arguments": {"days": 1}}
    reply1, _, ctx1 = execute_tool_call(call1, storage, "user_1", tz_name="Asia/Kolkata")
    assert "Daily Scrum" in reply1
    assert ctx1["type"] == "calendar"

    # Test short form: agenda
    call2 = {"name": "agenda", "arguments": {}}
    reply2, _, ctx2 = execute_tool_call(call2, storage, "user_1", tz_name="Asia/Kolkata")
    assert "Daily Scrum" in reply2
    assert ctx2["type"] == "calendar"
