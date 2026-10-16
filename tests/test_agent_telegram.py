import zoneinfo
from datetime import datetime, timedelta
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
        admin_chat_id="123456789",
        report_chat_id="-1001234567890",
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
        "chat": {"id": -1001234567890},
        "from": {"id": 12345},
        "text": "Hello group"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_report_group)
        mock_send.assert_not_called()

def test_command_time(bot):
    msg = {
        "message_id": 10,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/time"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == 123456789
        assert "Asia/Kolkata" in args[1]

def test_command_tasks(bot, mock_storage):
    mock_storage.create_task("123456789", "Test item 1")
    msg = {
        "message_id": 11,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
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
    tid = mock_storage.create_task("123456789", "Task to complete")
    cb = {
        "id": "cb123",
        "from": {"id": 123456789},
        "message": {
            "message_id": 20,
            "chat": {"id": 123456789},
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
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
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
        tasks = mock_storage.get_tasks("123456789")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Boil Eggs"
        assert tasks[0]["list_name"] == "timer"

def test_tool_call_task(bot, mock_storage):
    tool_xml = """<tool_call>
{"name": "add_task", "arguments": {"title": "Buy oat milk", "list_name": "groceries"}}
</tool_call>"""
    msg = {
        "message_id": 31,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "Add buy oat milk to my groceries list"
    }
    with patch.object(bot, "_query_daemon", return_value=tool_xml), \
         patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "Buy oat milk" in args[1]
        assert "[groceries]" in args[1]
        tasks = mock_storage.get_tasks("123456789")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Buy oat milk"
        assert tasks[0]["list_name"] == "groceries"

def test_tool_call_web_search(bot):
    tool_xml = """<tool_call>
{"name": "web_search", "arguments": {"query": "Mars rover status"}}
</tool_call>"""
    msg = {
        "message_id": 32,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
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

def test_conversational_weather(bot):
    msg = {
        "message_id": 40,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "how is the weather in kolkata?"
    }
    with patch("pithon.agent.telegram_bot.get_weather_report", return_value={"summary": "🌤️ Weather for Kolkata: 30°C"}), \
         patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert "30°C" in args[1]
        assert "Kolkata" in args[1]

def test_conversational_calculate(bot):
    msg = {
        "message_id": 41,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "what is 25 * 4?"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert "100" in args[1]

def test_command_task_and_note_and_search(bot, mock_storage, tmp_path):
    # Test /task
    msg_task = {
        "message_id": 50,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/task Buy vegetables tomorrow"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_task)
        mock_send.assert_called_once()
        assert "Buy vegetables" in mock_send.call_args[0][1]

    # Test /note
    msg_note = {
        "message_id": 51,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/note server-ip 192.168.1.100"
    }
    with patch("pithon.agent.telegram_bot.save_note", return_value={"filename": "server-ip.md"}) as mock_save,          patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_note)
        mock_save.assert_called_once_with("server-ip", "192.168.1.100", tz_name="Asia/Kolkata", base_dir=mock_storage.notes_dir())
        mock_send.assert_called_once()
        assert "Saved note" in mock_send.call_args[0][1]

    # Test /search
    msg_search = {
        "message_id": 52,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/search python async"
    }
    with patch("pithon.agent.telegram_bot.search_duckduckgo", return_value=[{"title": "Python Async", "href": "https://python.org", "body": "Async docs"}]) as mock_ddg,          patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_search)
        mock_ddg.assert_called_once_with("python async", max_results=3)
        mock_send.assert_called_once()
        assert "Python Async" in mock_send.call_args[0][1]


def test_command_calendar(bot, mock_storage):
    admin_id = "123456789"
    mock_storage.save_user_profile(admin_id, name="Pranabesh")
    mock_storage.update_calendar_settings(admin_id, url="https://example.com/cal.ics", alert_mins=10)

    # 1. /calendar view
    msg_cal = {
        "message_id": 60,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/calendar"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_cal)
        mock_send.assert_called_once()
        assert "Calendar" in mock_send.call_args[0][1]

    # 2. /calendar set <url>
    msg_set = {
        "message_id": 61,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/calendar set https://test.com/events.ics"
    }
    with patch("pithon.agent.calendar.fetch_and_parse_calendar", return_value=(True, "md5_new", [])) as mock_sync,          patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_set)
        mock_send.assert_called_once()
        assert "configured" in mock_send.call_args[0][1].lower()

    # 3. /calendar alert <mins>
    msg_alert = {
        "message_id": 62,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/calendar alert 15"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg_alert)
        mock_send.assert_called_once()
        assert "15 minutes" in mock_send.call_args[0][1]

    # 4. Callback cal_dismiss
    cb_dismiss = {
        "id": "cb_cal",
        "from": {"id": 123456789},
        "message": {
            "message_id": 63,
            "chat": {"id": 123456789},
            "text": "Meeting reminder"
        },
        "data": "cal_dismiss:event_1"
    }
    with patch.object(bot, "answer_callback_query") as mock_ans,          patch.object(bot, "edit_message_text") as mock_edit:
        bot.handle_callback_query(cb_dismiss)
        mock_ans.assert_called_once_with("cb_cal", text="Meeting reminder acknowledged! ✅")
        mock_edit.assert_called_once()


def test_command_calender_typo(bot, mock_storage):
    admin_id = "123456789"
    mock_storage.save_user_profile(admin_id, name="Pranabesh")
    mock_storage.update_calendar_settings(admin_id, url="https://example.com/cal.ics", alert_mins=10)

    # Typo: /calender (with an e)
    msg = {
        "message_id": 70,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "/calender"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        assert "Calendar" in mock_send.call_args[0][1]

def test_conversational_agenda_intent(bot, mock_storage):
    admin_id = "123456789"
    mock_storage.save_user_profile(admin_id, name="Pranabesh")
    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=3)).isoformat()
    mock_storage.save_calendar_events(admin_id, [{
        "id": "e-call-1",
        "parent_uid": "e-call-1",
        "title": "Support Team Sync",
        "description": "",
        "location": "Zoom",
        "meeting_link": "https://zoom.us/j/123",
        "start_time": start_time,
        "end_time": end_time,
        "is_recurring": 0,
        "event_md5": "md5-test"
    }])

    # Exact user query from conversation: 'Hi , what is In my agenda'
    msg = {
        "message_id": 71,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "Hi , what is In my agenda"
    }
    with patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        reply_text = mock_send.call_args[0][1]
        assert "Support Team Sync" in reply_text
        assert "https://zoom.us/j/123" in reply_text

def test_model_tool_call_get_calendar_events(bot, mock_storage):
    admin_id = "123456789"
    mock_storage.save_user_profile(admin_id, name="Pranabesh")
    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=3)).isoformat()
    mock_storage.save_calendar_events(admin_id, [{
        "id": "e-cal-2",
        "parent_uid": "e-cal-2",
        "title": "Architecture Review",
        "description": "",
        "location": "Google Meet",
        "meeting_link": "https://meet.google.com/abc",
        "start_time": start_time,
        "end_time": end_time,
        "is_recurring": 0,
        "event_md5": "md5-cal-2"
    }])

    # Simulate Qwen outputting un-underscored JSON without XML tags
    tool_json = '{"name": "getcalendarevents", "arguments": {"days": 1}}'
    msg = {
        "message_id": 72,
        "chat": {"id": 123456789},
        "from": {"id": 123456789},
        "text": "Any upcoming events?"
    }
    with patch.object(bot, "_query_daemon", return_value=tool_json),          patch.object(bot, "send_message") as mock_send:
        bot.handle_message(msg)
        mock_send.assert_called_once()
        reply = mock_send.call_args[0][1]
        # Must execute the tool call, NOT print raw JSON!
        assert "{" not in reply
        assert "Architecture Review" in reply


def test_callback_edits_do_not_use_markdownv2_strikethrough(mock_storage):
    """Regression: ~~x~~ is MarkdownV2-only and renders as literal tildes.

    The bot sends parse_mode="Markdown" (legacy), which has no strikethrough, so
    the old text was left visibly wrapped in tildes after every Done/Del click.
    """
    from pithon.agent.telegram_bot import TelegramBot

    admin_id = "123456789"
    bot = TelegramBot(token="t", admin_chat_id=admin_id, storage=mock_storage)
    tid = mock_storage.create_task(admin_id, "Buy milk")

    with patch.object(bot, "answer_callback_query") as mock_ack, \
         patch.object(bot, "edit_message_text") as mock_edit:
        bot.handle_callback_query({
            "id": "cb1",
            "from": {"id": int(admin_id)},
            "data": f"done:{tid}",
            "message": {"message_id": 1, "chat": {"id": int(admin_id)}, "text": "📋 Buy milk"},
        })
        mock_ack.assert_called_once()
        edited = mock_edit.call_args[0][2]
        assert "~~" not in edited
        # The original message is preserved rather than mangled.
        assert "📋 Buy milk" in edited
        assert "Marked completed" in edited
        assert mock_storage.get_task_by_id(tid)["is_completed"] == 1

        bot.handle_callback_query({
            "id": "cb2",
            "from": {"id": int(admin_id)},
            "data": f"del:{tid}",
            "message": {"message_id": 1, "chat": {"id": int(admin_id)}, "text": "📋 Buy milk"},
        })
        deleted = mock_edit.call_args[0][2]
        assert "~~" not in deleted
        assert "Deleted" in deleted
        assert mock_storage.get_task_by_id(tid) is None


def test_slm_output_is_sent_without_parse_mode(mock_storage):
    """A stray '*' in a 0.5B completion would otherwise 400 the whole message."""
    from pithon.agent.telegram_bot import TelegramBot

    admin_id = "123456789"
    bot = TelegramBot(token="t", admin_chat_id=admin_id, storage=mock_storage)
    with patch.object(bot, "_query_daemon", return_value="Here is a *broken* answer"), \
         patch.object(bot, "send_message") as mock_send, \
         patch.object(bot, "send_chat_action"):
        bot.handle_message({
            "message_id": 5,
            "chat": {"id": int(admin_id)},
            "from": {"id": int(admin_id)},
            "text": "Explain Raft consensus in detail",
        })
        assert mock_send.called
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("parse_mode") is None
        # Deterministic replies keep Markdown; only model output drops it.
        assert mock_send.call_args[0][1] == "Here is a *broken* answer"
