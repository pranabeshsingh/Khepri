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
