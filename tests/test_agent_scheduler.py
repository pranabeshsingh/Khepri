import pytest
import sqlite3
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
    admin_id = "123456789"
    report_id = "-1001234567890"
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
    admin_id = "123456789"
    report_id = "-1001234567890"
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


def test_calendar_alerts_tick(temp_storage, mock_bot):
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    temp_storage.save_user_profile(admin_id, name="Pranabesh")
    temp_storage.update_calendar_settings(admin_id, url="https://example.com/cal.ics", alert_mins=10, feed_md5="")

    now = datetime.now(timezone.utc)
    start = (now + timedelta(minutes=5)).isoformat()
    end = (now + timedelta(minutes=35)).isoformat()
    temp_storage.save_calendar_events(admin_id, [{
        "id": "event-1",
        "parent_uid": "event-1",
        "title": "Live Call",
        "description": "Join https://meet.google.com/xyz",
        "location": "Google Meet",
        "meeting_link": "https://meet.google.com/xyz",
        "start_time": start,
        "end_time": end,
        "is_recurring": 0,
        "event_md5": "md5-1"
    }])

    dispatched = scheduler.calendar_alerts_tick()
    assert dispatched == 1
    mock_bot.send_message.assert_called_once()
    args, kwargs = mock_bot.send_message.call_args
    assert str(args[0]) == admin_id
    assert "Live Call" in args[1]
    assert kwargs.get("disable_web_page_preview") is True
    buttons = kwargs["reply_markup"]["inline_keyboard"][0]
    assert any(b.get("url") == "https://meet.google.com/xyz" for b in buttons)

    mock_bot.send_message.reset_mock()
    dispatched_again = scheduler.calendar_alerts_tick()
    assert dispatched_again == 0
    mock_bot.send_message.assert_not_called()

def test_calendar_sync_tick(temp_storage, mock_bot):
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    temp_storage.update_calendar_settings(admin_id, url="https://example.com/cal.ics", alert_mins=10, feed_md5="")

    sample_events = [{
        "id": "synced-1",
        "parent_uid": "synced-1",
        "title": "Synced Standup",
        "description": "",
        "location": "",
        "meeting_link": "",
        "start_time": datetime.now(timezone.utc) + timedelta(hours=1),
        "end_time": datetime.now(timezone.utc) + timedelta(hours=2),
        "is_recurring": 0,
        "event_md5": "md5-synced"
    }]

    with patch("pithon.agent.scheduler.fetch_and_parse_calendar", return_value=(True, "new_feed_md5", sample_events)):
        synced = scheduler.calendar_sync_tick()
        assert synced == 1
        prof = temp_storage.get_user_profile(admin_id)
        assert prof["calendar_feed_md5"] == "new_feed_md5"
        upcoming = temp_storage.get_upcoming_events(admin_id)
        assert len(upcoming) == 1
        assert upcoming[0]["title"] == "Synced Standup"

def test_scheduler_evening_wrapup(mock_bot, temp_storage):
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    temp_storage.create_task(admin_id, "Pending Test Task")
    tid_done = temp_storage.create_task(admin_id, "Completed Test Task")
    temp_storage.complete_task(tid_done)

    wrapup = scheduler.evening_wrapup_tick()
    assert "Evening Wrap-up" in wrapup
    assert "Completed Tasks" in wrapup
    assert "Pending Carryover Tasks" in wrapup
    mock_bot.send_message.assert_called_once()


def _backdate_last_interaction(db_path, when_utc):
    """Rewrite the newest interactions row's created_at.

    log_interaction stamps CURRENT_TIMESTAMP, but the compactor's window is a
    real date filter, so exercising it needs rows that are actually yesterday.
    Written with plain sqlite3 rather than a new production API purely for tests.
    """
    stamp = when_utc.strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE interactions SET created_at = ? WHERE id = (SELECT MAX(id) FROM interactions)",
            (stamp,)
        )
        conn.commit()
    finally:
        conn.close()


def test_scheduler_compact_memory(mock_bot, temp_storage, tmp_path):
    db_path = str(tmp_path / "sched_test.db")
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    # Yesterday's turn: must be summarised.
    temp_storage.log_interaction(
        chat_id=admin_id,
        user_id=admin_id,
        prompt="Discussed cgroup memory configuration for Docker container",
        response="Noted, cgroup limit is 512MB."
    )
    _backdate_last_interaction(db_path, datetime.now(timezone.utc) - timedelta(days=1))
    # Today's turn: must NOT leak into yesterday's summary.
    temp_storage.log_interaction(
        chat_id=admin_id,
        user_id=admin_id,
        prompt="Discussed today's unrelated deploy rollback",
        response="Rolled back cleanly."
    )

    summary = scheduler.compact_memory_tick()
    assert summary is not None
    assert "Daily Conversation Summary" in summary
    assert "cgroup memory" in summary
    # Regression guard: the compactor used to take the last N turns regardless
    # of date, so today's conversation was filed under yesterday's heading.
    assert "deploy rollback" not in summary


def test_scheduler_compact_memory_skips_when_nothing_recorded_yesterday(mock_bot, temp_storage):
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    # Only today. Summarising it as "yesterday" would be a data-integrity bug,
    # so the tick must no-op rather than fabricate a note.
    temp_storage.log_interaction(
        chat_id=admin_id,
        user_id=admin_id,
        prompt="Only a conversation from today",
        response="Acknowledged."
    )
    assert scheduler.compact_memory_tick() is None


def test_evening_wrapup_counts_only_todays_completions(mock_bot, temp_storage):
    """completed_at is stamped in UTC; the day window must be built in UTC too."""
    admin_id = "admin_1"
    scheduler = Scheduler(
        bot=mock_bot,
        storage=temp_storage,
        admin_chat_id=admin_id,
        tz_name="Asia/Kolkata"
    )
    today_done = temp_storage.create_task(admin_id, "Completed today")
    temp_storage.complete_task(today_done)

    # Simulate a task finished a day ago by rewriting completed_at directly.
    older_done = temp_storage.create_task(admin_id, "Completed yesterday")
    temp_storage.complete_task(older_done)
    conn = sqlite3.connect(temp_storage.db_path)
    try:
        conn.execute(
            "UPDATE tasks SET completed_at = ? WHERE title = ?",
            (
                (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "Completed yesterday",
            )
        )
        conn.commit()
    finally:
        conn.close()

    wrapup = scheduler.evening_wrapup_tick()
    # Exactly one completion belongs to today, not the all-time total.
    assert "• *Completed Tasks:* `1`" in wrapup


def test_completed_at_cleared_on_toggle(mock_bot, temp_storage):
    """Re-opening a task must drop completed_at, or it resurfaces in day counts."""
    tid = temp_storage.create_task("admin_1", "Toggle me")
    temp_storage.complete_task(tid)
    conn = sqlite3.connect(temp_storage.db_path)
    try:
        assert conn.execute(
            "SELECT completed_at FROM tasks WHERE id = ?", (tid,)
        ).fetchone()[0] is not None
    finally:
        conn.close()

    assert temp_storage.toggle_task(tid) is False
    conn = sqlite3.connect(temp_storage.db_path)
    try:
        assert conn.execute(
            "SELECT completed_at FROM tasks WHERE id = ?", (tid,)
        ).fetchone()[0] is None
    finally:
        conn.close()
