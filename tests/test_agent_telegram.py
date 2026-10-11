import pytest
from unittest.mock import patch, MagicMock
from pithon.agent.telegram_bot import TelegramBot
from pithon.agent.storage import Storage

@pytest.fixture
def mock_storage(tmp_path):
    db_path = str(tmp_path / "bot_test.db")
    return Storage(db_path)

@pytest.fixture
def bot(mock_storage):
    return TelegramBot(
        token="test-token",
        admin_chat_id="357035668",
        report_chat_id="-1001169201210",
        storage=mock_storage,
        daemon_url="http://127.0.0.1:8090",
        tz_name="Asia/Kolkata"
    )

def test_whitelist_rejection(bot):
    # Untrusted user
    msg_untrusted = {
        "message_id": 1,
        "chat": {"id": 999999999},
        "from": {"id": 999999999},
        "text": "Hello"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_untrusted)
        mock_send.assert_not_called()

    # Report group inbound message should also be silently ignored
    msg_report_group = {
        "message_id": 2,
        "chat": {"id": -1001169201210},
        "from": {"id": 12345},
        "text": "Hello group"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_report_group)
        mock_send.assert_not_called()

def test_command_time(bot):
    msg = {
        "message_id": 10,
        "chat": {"id": 357035668},
        "from": {"id": 357035668},
        "text": "/time"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == 357035668
        assert "Asia/Kolkata" in args[1]

def test_command_tasks(bot, mock_storage):
    mock_storage.create_task("357035668", "Test item 1")
    msg = {
        "message_id": 11,
        "chat": {"id": 357035668},
        "from": {"id": 357035668},
        "text": "/todo"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "Test item 1" in args[1]
        assert "reply_markup" in kwargs
        assert "inline_keyboard" in kwargs["reply_markup"]

def test_callback_query_done(bot, mock_storage):
    tid = mock_storage.create_task("357035668", "Task to complete")
    cb = {
        "id": "cb123",
        "from": {"id": 357035668},
        "message": {
            "message_id": 20,
            "chat": {"id": 357035668},
            "text": "Task to complete"
        },
        "data": f"done:{tid}"
    }
    with patch.object(bot, "answer_callback_query") as mock_ans, \
         patch.object(bot, "edit_message_text") as mock_edit:
        bot.handle_callback_query(cb)
        mock_ans.assert_called_once_with("cb123", text="Task marked complete! ✅")
        mock_edit.assert_called_once()
        assert mock_storage.get_task_by_id(tid)["is_completed"] == 1

def test_tool_call_timer(bot, mock_storage):
    tool_xml = """<tool_call>
{"name": "set_timer", "arguments": {"duration": 15, "unit": "minutes", "label": "Boil Eggs"}}
</tool_call>"""
    msg = {
        "message_id": 30,
        "chat": {"id": 357035668},
        "from": {"id": 357035668},
        "text": "Can you set a timer for 15 mins to boil eggs?"
    }
    with patch.object(bot, "_query_daemon", return_value=tool_xml), \
         patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "Timer set:" in args[1]
        assert "Boil Eggs" in args[1]
        assert "reply_markup" in kwargs
        assert "inline_keyboard" in kwargs["reply_markup"]

        # Verify task created in database
        tasks = mock_storage.get_tasks("357035668")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Boil Eggs"
        assert tasks[0]["list_name"] == "timer"

def test_tool_call_task(bot, mock_storage):
    tool_xml = """<tool_call>
{"name": "add_task", "arguments": {"title": "Buy oat milk", "list_name": "groceries"}}
</tool_call>"""
    msg = {
        "message_id": 31,
        "chat": {"id": 357035668},
        "from": {"id": 357035668},
        "text": "Add buy oat milk to my groceries list"
    }
    with patch.object(bot, "_query_daemon", return_value=tool_xml), \
         patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "Buy oat milk" in args[1]
        assert "[groceries]" in args[1]
        tasks = mock_storage.get_tasks("357035668")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Buy oat milk"
        assert tasks[0]["list_name"] == "groceries"

def test_tool_call_web_search(bot):
    tool_xml = """<tool_call>
{"name": "web_search", "arguments": {"query": "Mars rover status"}}
</tool_call>"""
    msg = {
        "message_id": 32,
        "chat": {"id": 357035668},
        "from": {"id": 357035668},
        "text": "What is the latest status of Mars rover?"
    }
    with patch.object(bot, "_query_daemon", side_effect=[tool_xml, "Perseverance is currently exploring Jezero Crater."]), \
         patch("pithon.agent.tools.search_duckduckgo", return_value=[{"title": "NASA Mars", "snippet": "Active", "url": "https://mars.nasa.gov"}]), \
         patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "Perseverance is currently exploring" in args[1]
        assert "reply_markup" in kwargs
        assert kwargs["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://mars.nasa.gov"
