import os
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from pithon.agent.storage import Storage

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_pithon.db")
        storage = Storage(db_path)
        yield storage

def test_storage_init(temp_storage):
    # Verify tables created without error
    tables = temp_storage.get_table_names()
    assert "interactions" in tables
    assert "tasks" in tables
    assert "digests" in tables
    assert "sessions" in tables

def test_interaction_lifecycle(temp_storage):
    idx = temp_storage.log_interaction(
        chat_id="123456789",
        user_id="user1",
        prompt="What is the weather?",
        search_query="weather kolkata",
        search_results=[{"title": "Weather", "snippet": "28C Sunny", "url": "https://weather.com"}],
        response="It is 28C and sunny in Kolkata.",
        latency_ms=120
    )
    assert idx > 0

    items = temp_storage.get_interactions(limit=10)
    assert len(items) == 1
    assert items[0]["prompt"] == "What is the weather?"
    assert items[0]["latency_ms"] == 120
    assert len(items[0]["search_results"]) == 1

    # Filter search
    found = temp_storage.get_interactions(search_term="kolkata")
    assert len(found) == 1
    not_found = temp_storage.get_interactions(search_term="nonexistent")
    assert len(not_found) == 0

def test_task_lifecycle(temp_storage):
    chat_id = "123456789"
    task_id = temp_storage.create_task(
        chat_id=chat_id,
        title="Renew domain name",
        list_name="work",
        due_at="2026-10-12T16:00:00+05:30"
    )
    assert task_id > 0

    tasks = temp_storage.get_tasks(chat_id=chat_id, list_name="work")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Renew domain name"
    assert tasks[0]["is_completed"] == 0

    # Snooze task
    assert temp_storage.snooze_task(task_id, hours=2) is True
    updated = temp_storage.get_task_by_id(task_id)
    assert updated["due_at"] != "2026-10-12T16:00:00+05:30"

    # Complete task
    assert temp_storage.complete_task(task_id) is True
    completed_tasks = temp_storage.get_tasks(chat_id=chat_id, include_completed=True)
    assert completed_tasks[0]["is_completed"] == 1

    # Delete task
    assert temp_storage.delete_task(task_id) is True
    assert len(temp_storage.get_tasks(chat_id=chat_id, include_completed=True)) == 0

def test_pending_reminders(temp_storage):
    chat_id = "123456789"
    past_due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    t_id = temp_storage.create_task(chat_id=chat_id, title="Overdue task", due_at=past_due)

    now_iso = datetime.now(timezone.utc).isoformat()
    pending = temp_storage.get_pending_reminders(now_iso)
    assert len(pending) == 1
    assert pending[0]["id"] == t_id

    temp_storage.mark_reminded(t_id)
    pending_after = temp_storage.get_pending_reminders(now_iso)
    assert len(pending_after) == 0

def test_digests(temp_storage):
    d_id = temp_storage.log_digest(
        target_chat_id="-1001234567890",
        summary_text="Hourly activity: 3 queries.",
        period_start="2026-10-11T14:00:00",
        period_end="2026-10-11T15:00:00",
        interaction_count=3,
        sent_silent=True
    )
    assert d_id > 0
    digests = temp_storage.get_digests(limit=5)
    assert len(digests) == 1
    assert digests[0]["interaction_count"] == 3

def test_sessions(temp_storage):
    token = "secret-session-token"
    temp_storage.create_session(token=token, expires_in_sec=3600)
    assert temp_storage.validate_session(token) is True
    assert temp_storage.validate_session("bad-token") is False


def test_calendar_events_storage(temp_storage):
    events = [
        {
            "id": "call-1#2026-10-13T10:00:00",
            "parent_uid": "call-1",
            "title": "Design Review",
            "description": "Review specs",
            "location": "Meet",
            "meeting_link": "https://meet.google.com/abc",
            "start_time": "2026-10-13T10:00:00+05:30",
            "end_time": "2026-10-13T10:30:00+05:30",
            "is_recurring": 0,
            "event_md5": "md5_hash_1"
        }
    ]
    upserted = temp_storage.save_calendar_events("123", events)
    assert upserted == 1

    # Second call with same event_md5 should not touch rows
    upserted_again = temp_storage.save_calendar_events("123", events)
    assert upserted_again == 0

    upcoming = temp_storage.get_upcoming_events("123", limit=5, start_after="2026-10-13T09:00:00+05:30")
    assert len(upcoming) == 1
    assert upcoming[0]["meeting_link"] == "https://meet.google.com/abc"

    # Unreminded range query
    unreminded = temp_storage.get_unreminded_events_in_range(
        "123",
        "2026-10-13T09:00:00+05:30",
        "2026-10-13T10:15:00+05:30"
    )
    assert len(unreminded) == 1
    assert unreminded[0]["id"] == "call-1#2026-10-13T10:00:00"

    # Mark reminded
    temp_storage.mark_event_reminded("call-1#2026-10-13T10:00:00")
    unreminded_after = temp_storage.get_unreminded_events_in_range(
        "123",
        "2026-10-13T09:00:00+05:30",
        "2026-10-13T10:15:00+05:30"
    )
    assert len(unreminded_after) == 0

    # Settings update
    temp_storage.update_calendar_settings("123", url="https://example.com/cal.ics", alert_mins=15, feed_md5="feed123")
    prof = temp_storage.get_user_profile("123")
    assert prof["calendar_url"] == "https://example.com/cal.ics"
    assert prof["calendar_alert_mins"] == 15
    assert prof["calendar_feed_md5"] == "feed123"

    # Pruning old events
    pruned = temp_storage.prune_old_calendar_events(days=0)
    assert pruned == 1
    assert len(temp_storage.get_upcoming_events("123", limit=5, start_after="2026-10-13T09:00:00+05:30")) == 0
