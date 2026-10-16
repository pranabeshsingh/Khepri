import pytest
from unittest.mock import patch
from pithon.agent.router import (
    is_time_intent,
    is_status_intent,
    is_notes_search_intent,
    is_math_intent,
    route_fast_path
)
from pithon.agent.storage import Storage

def test_router_intent_checkers():
    assert is_time_intent("what time is it") is True
    assert is_time_intent("tell me the time") is True
    assert is_time_intent("what day is today") is True
    assert is_time_intent("hello there") is False

    assert is_status_intent("system status") is True
    assert is_status_intent("uptime") is True
    assert is_status_intent("how are you") is False

    assert is_notes_search_intent("search notes for docker") == "docker"
    assert is_notes_search_intent("find notes on vps") == "vps"
    assert is_notes_search_intent("general question") is None

    assert is_math_intent("what is 450 * 1.18 + 32") == "450 * 1.18 + 32"
    assert is_math_intent("what is 4320 / 6?") == "4320 / 6"
    assert is_math_intent("calculate 25 * 4") == "25 * 4"
    assert is_math_intent("1024 * 64") == "1024 * 64"
    assert is_math_intent("explain python") is None
    assert is_math_intent("what is the weather?") is None

    # ReDoS resilience test
    import time
    long_expr = "what is " + " " * 500 + "42 * 2?"
    t0 = time.time()
    res = is_math_intent(long_expr)
    assert time.time() - t0 < 0.1
    assert res == "42 * 2"

def test_route_fast_path_time(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("what time is it", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, markup, ctx = res
    assert "Current Date & Time" in reply_text
    assert ctx["type"] == "time"

def test_route_fast_path_math(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("what is 100 * 5", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, markup, ctx = res
    assert "500" in reply_text
    assert ctx["type"] == "calc"

def test_route_fast_path_status(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("system health", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, markup, ctx = res
    assert "Khepri System Health" in reply_text
    assert ctx["type"] == "status"

def test_route_fast_path_unmatched(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    # Complex query should fall through (return None)
    res = route_fast_path("Explain the Raft consensus algorithm", storage, "123", tz_name="Asia/Kolkata")
    assert res is None


def test_route_fast_path_notes_browse(tmp_path):
    """/notes must reach both surfaces, not just Telegram."""
    from pithon.agent.memory import save_note

    storage = Storage(str(tmp_path / "test.db"))
    save_note("server specs", "4 core ARM", base_dir=storage.notes_dir())
    res = route_fast_path("/notes", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, _markup, ctx = res
    assert "Saved Markdown Notes" in reply_text
    assert ctx["type"] == "notes"


def test_route_fast_path_notes_browse_empty(tmp_path):
    """Storage.__init__ seeds a starter note, so empty the vault explicitly."""
    import os

    storage = Storage(str(tmp_path / "test.db"))
    notes_dir = storage.notes_dir()
    for fname in os.listdir(notes_dir):
        os.remove(os.path.join(notes_dir, fname))

    res = route_fast_path("/notes", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, _markup, ctx = res
    assert "No saved notes" in reply_text
    assert ctx["count"] == 0


def test_calendar_set_subcommand_precedes_event_listing(tmp_path):
    """Regression: a surface matching startswith('/calendar') dropped the URL.

    The subcommand must win over the read-only listing, or the feed URL is
    silently discarded.
    """
    storage = Storage(str(tmp_path / "test.db"))
    with patch("pithon.agent.calendar.fetch_and_parse_calendar", return_value=(True, "md5abc", [])):
        res = route_fast_path(
            "/calendar set https://example.com/feed.ics", storage, "123", tz_name="Asia/Kolkata"
        )
    assert res is not None
    reply_text, _markup, ctx = res
    assert "configured" in reply_text.lower()
    assert ctx.get("configured") is True
    assert storage.get_user_profile("123").get("calendar_url") == "https://example.com/feed.ics"


def test_calendar_alert_subcommand_validates_range(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("/calendar alert 15", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, _markup, ctx = res
    assert "15 minutes" in reply_text
    assert ctx.get("alert_mins") == 15

    bad = route_fast_path("/calendar alert 9999", storage, "123", tz_name="Asia/Kolkata")
    assert bad is not None
    assert "between 1 and 120" in bad[0]


def test_calendar_set_rejects_non_http_scheme(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("/calendar set file:///etc/passwd", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    assert "Invalid URL" in res[0]


def test_bare_arithmetic_reaches_router(tmp_path):
    """Bare expressions were portal-unreachable before the route_fast_path delegation."""
    storage = Storage(str(tmp_path / "test.db"))
    res = route_fast_path("450 * 1.18 + 32", storage, "123", tz_name="Asia/Kolkata")
    assert res is not None
    reply_text, _markup, ctx = res
    assert ctx["type"] == "calc"
    assert "563" in reply_text
