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
