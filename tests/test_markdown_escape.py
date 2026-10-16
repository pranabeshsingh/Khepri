"""Unit tests for Telegram legacy Markdown escaping.

The regression these guard against is silent: an unbalanced marker makes the Bot
API answer 400 "can't parse entities", and TelegramBot._call_api swallows the
error, so the originating command appears to do nothing at all.
"""

from pithon.agent.markdown_escape import escape_markdown, escape_code
from pithon.agent.tasks import format_tasks_message, format_reminder_alert
from pithon.agent.tools import execute_tool_call
from pithon.agent.storage import Storage


def test_escape_covers_every_legacy_metacharacter():
    raw = r"a_b*c`d[e]f\g"
    out = escape_markdown(raw)
    assert out == "a\\_b\\*c\\`d\\[e\\]f\\\\g"


def test_escape_leaves_ordinary_text_untouched():
    assert escape_markdown("Deploy v0.2 tomorrow at 5pm") == "Deploy v0.2 tomorrow at 5pm"


def test_escape_is_idempotent_only_for_pure_text():
    # Escaping twice must not double-escape the escape characters themselves:
    # str.translate runs in a single pass, so it cannot.
    once = escape_markdown("a*b")
    assert once == "a\\*b"
    assert escape_markdown("a\\b") == "a\\\\b"


def test_escape_handles_non_strings_and_none():
    assert escape_markdown(None) == ""
    assert escape_markdown(42) == "42"


def test_escape_code_leaves_normal_backticks_alone():
    # One or two backticks cannot close a triple-backtick fence.
    assert escape_code("a`b``c") == "a`b``c"


def test_escape_code_neutralises_fence_breaking_runs():
    out = escape_code("before ``` after")
    assert "```" not in out
    assert "\u200b" in out
    # Still visually the same text.
    assert out.replace("\u200b", "") == "before ``` after"


def test_task_title_with_markdown_cannot_break_the_message(tmp_path):
    """A title containing every marker is the exact shape that produced silent 400s."""
    storage = Storage(str(tmp_path / "t.db"))
    hostile = "Review *urgent* [draft] `_notes` + \\escape"
    tid = storage.create_task("chat", hostile)

    msg, _kb = format_tasks_message(storage.get_tasks("chat"))
    assert "Review \\*urgent\\*" in msg
    assert "[draft]" not in msg  # brackets neutralised
    assert "\\[draft\\]" in msg

    alert, _kb2 = format_reminder_alert(
        {"id": tid, "title": hostile, "due_at": "2026-10-17T09:00:00"}
    )
    assert "\\*urgent\\*" in alert

    # Balanced after escaping: no unescaped marker survives in user content.
    assert msg.count("*") % 2 == 0


def test_reminder_alert_timer_detection_uses_raw_title(tmp_path):
    """Escaping must not happen before the 'timer' substring test."""
    msg, kb = format_reminder_alert({"id": 1, "title": "Pasta *timer*", "due_at": None})
    assert "TIMER UP" in msg
    assert "\\*timer\\*" in msg


def test_tool_add_task_escapes_model_supplied_title(tmp_path):
    storage = Storage(str(tmp_path / "t.db"))
    reply, _markup, _ctx = execute_tool_call(
        {"name": "add_task", "arguments": {"title": "buy *milk* and [eggs]"}},
        storage,
        "chat",
    )
    assert "\\*milk\\*" in reply
    assert "\\[eggs\\]" in reply


def test_tool_search_notes_escapes_note_bodies(tmp_path):
    from pithon.agent.memory import save_note

    storage = Storage(str(tmp_path / "t.db"))
    save_note("server", "host is up *and* `_down`", base_dir=storage.notes_dir())
    reply, _markup, _ctx = execute_tool_call(
        {"name": "search_notes", "arguments": {"query": "server"}},
        storage,
        "chat",
    )
    assert "\\*and\\*" in reply
    # The note body's literal backticks and underscores are both neutralised.
    assert "\\`\\_down\\`" in reply
    # Every surviving backtick is escaped, so none can open or close a code span.
    body = reply.rsplit(":\n", 1)[1]
    assert all(body[i - 1] == "\\" for i, c in enumerate(body) if c == "`" and i > 0)


def test_tool_calendar_events_escape_event_titles(tmp_path):
    import zoneinfo
    from datetime import datetime, timedelta

    storage = Storage(str(tmp_path / "t.db"))
    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).replace(hour=14, minute=0, second=0, microsecond=0)
    storage.save_calendar_events("chat", [{
        "id": "e1",
        "parent_uid": "p1",
        "title": "Budget *review* [Q3]",
        "description": "",
        "location": "Room _A_",
        "meeting_link": "",
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(minutes=30)).isoformat(),
        "is_recurring": 0,
        "event_md5": "m1",
    }])
    reply, _markup, _ctx = execute_tool_call(
        {"name": "get_calendar_events", "arguments": {"days": 1}},
        storage,
        "chat",
    )
    assert "\\*review\\*" in reply
    assert "\\[Q3\\]" in reply
    assert "\\_A\\_" in reply
