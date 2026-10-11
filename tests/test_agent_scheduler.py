import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from pithon.agent.scheduler import Scheduler
from pithon.agent.storage import Storage

@pytest.fixture
def temp_storage(tmp_path):
    db_path = str(tmp_path / "sched_test.db")
    return Storage(db_path)

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    return bot

def test_check_reminders_tick(temp_storage, mock_bot):
    admin_id = "357035668"
    report_id = "-1001169201210"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        report_chat_id=report_id,
        tz_name="Asia/Kolkata"
    )

    # Add task due 2 minutes ago
    past_due = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    tid = temp_storage.create_task(admin_id, "Take medication", due_at=past_due)

    # Run tick
    dispatched = scheduler.check_reminders_tick()
    assert dispatched == 1
    mock_bot.send_message.assert_called_once()
    args, kwargs = mock_bot.send_message.call_args
    assert str(args[0]) == admin_id
    assert "Take medication" in args[1]
    assert "reply_markup" in kwargs

    # Second tick should not resend
    mock_bot.send_message.reset_mock()
    assert scheduler.check_reminders_tick() == 0
    mock_bot.send_message.assert_not_called()

def test_hourly_digest_tick(temp_storage, mock_bot):
    admin_id = "357035668"
    report_id = "-1001169201210"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        report_chat_id=report_id,
        tz_name="Asia/Kolkata"
    )

    # Log 2 interactions
    temp_storage.log_interaction(admin_id, "u1", "Query 1", None, None, "Ans 1", 100)
    temp_storage.log_interaction(admin_id, "u1", "Query 2", "q2", [{"title": "t"}], "Ans 2", 150)

    digest_text = scheduler.hourly_digest_tick()
    assert "Pithon Hourly Digest" in digest_text
    assert "Total Interactions:" in digest_text

    # Verify sent to report group silently
    mock_bot.send_message.assert_called_once()
    args, kwargs = mock_bot.send_message.call_args
    assert str(args[0]) == report_id
    assert kwargs.get("disable_notification") is True
    assert "reply_markup" in kwargs

    # Verify saved in storage
    digests = temp_storage.get_digests()
    assert len(digests) == 1
