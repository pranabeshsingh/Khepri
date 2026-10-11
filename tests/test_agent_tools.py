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
    assert "Timer Started!" in reply
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
