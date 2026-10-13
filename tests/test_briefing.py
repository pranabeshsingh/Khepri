"""Unit tests for Khepri Daily Briefing, News aggregator, and Milestone Facts."""

from datetime import datetime
from unittest.mock import patch

from pithon.agent.briefing import generate_daily_briefing
from pithon.agent.facts import get_interesting_fact_today, get_thought_of_the_day
from pithon.agent.news import clean_headline, format_news_section, fetch_news_headlines
from pithon.agent.tools import execute_tool_call
from pithon.agent.storage import Storage


def test_interesting_facts_and_thoughts():
    dt = datetime(2026, 10, 11)
    fact = get_interesting_fact_today(dt)
    assert "Apollo 7" in fact

    thought = get_thought_of_the_day(dt)
    assert '"' in thought
    assert "—" in thought


def test_clean_headline():
    assert clean_headline("Breaking News &amp; Updates") == "Breaking News & Updates"
    assert clean_headline("  Multiple   spaces  ") == "Multiple spaces"


def test_format_news_section():
    mock_news = {
        "local": [{"title": f"Local News {i}", "url": ""} for i in range(1, 6)],
        "national": [{"title": f"National News {i}", "url": ""} for i in range(1, 4)],
        "world": [{"title": f"World News {i}", "url": ""} for i in range(1, 3)],
    }
    formatted = format_news_section(mock_news, city="Kolkata")
    assert "Top 10 Curated Headlines" in formatted
    assert "1. Local News 1" in formatted
    assert "5. Local News 5" in formatted
    assert "6. National News 1" in formatted
    assert "8. National News 3" in formatted
    assert "9. World News 1" in formatted
    assert "10. World News 2" in formatted


def test_format_news_section_with_urls():
    mock_news = {
        "local": [{"title": "Bengaluru Metro Opens - Deccan Herald", "url": "https://example.com/metro"}],
        "national": [{"title": "ISRO Lunar Mission Update - The Hindu", "url": "https://example.com/isro"}],
        "world": [{"title": "Global Climate Summit - BBC", "url": "https://example.com/climate"}],
    }
    formatted = format_news_section(mock_news, city="Bengaluru")
    assert "1. [Bengaluru Metro Opens](https://example.com/metro) — _Deccan Herald_" in formatted
    assert "6. [ISRO Lunar Mission Update](https://example.com/isro) — _The Hindu_" in formatted
    assert "9. [Global Climate Summit](https://example.com/climate) — _BBC_" in formatted


def test_generate_daily_briefing_standalone(tmp_path):
    db_path = str(tmp_path / "test_pithon.db")
    storage = Storage(db_path)
    storage.save_user_profile("12345", name="Pranabesh", city="Kolkata", focus="AI Systems")

    with patch("pithon.agent.briefing.fetch_news_headlines") as mock_fetch,          patch("pithon.agent.briefing.get_weather_report") as mock_weather:
        mock_fetch.return_value = {
            "local": [{"title": "Kolkata Tech Hub Opens", "url": ""}],
            "national": [{"title": "ISRO New Launch Successful", "url": ""}],
            "world": [{"title": "Global Climate Accord Signed", "url": ""}],
        }
        mock_weather.return_value = {"summary": "28°C Clear skies"}

        briefing = generate_daily_briefing("12345", storage, tz_name="Asia/Kolkata")
        assert "Pranabesh" in briefing
        assert "AI Systems" in briefing
        assert "Kolkata" in briefing
        assert "28°C Clear skies" in briefing
        assert "Kolkata Tech Hub Opens" in briefing
        assert "Interesting About Today" in briefing
        assert "Thought for Today" in briefing
        assert "Edge Status" in briefing


def test_execute_tool_call_briefing(tmp_path):
    db_path = str(tmp_path / "test_pithon.db")
    storage = Storage(db_path)
    storage.save_user_profile("web", name="Pranabesh", city="Bengaluru")

    with patch("pithon.agent.briefing.fetch_news_headlines") as mock_fetch,          patch("pithon.agent.briefing.get_weather_report") as mock_weather:
        mock_fetch.return_value = {
            "local": [{"title": "Bengaluru Metro Extension", "url": ""}],
            "national": [{"title": "India GDP Milestone", "url": ""}],
            "world": [{"title": "Space Mission Update", "url": ""}],
        }
        mock_weather.return_value = {"summary": "24°C Pleasant"}

        tool_call = {"name": "get_daily_briefing", "arguments": {"city": "Bengaluru"}}
        reply, markup, ctx = execute_tool_call(tool_call, storage, "web", tz_name="Asia/Kolkata")

        assert "Bengaluru Metro Extension" in reply
        assert ctx["type"] == "briefing"


def test_briefing_includes_agenda(tmp_path):
    import zoneinfo
    db_path = str(tmp_path / "test_pithon.db")
    storage = Storage(db_path)
    storage.save_user_profile("user_1", name="Pranabesh")
    now_local = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    start_iso = now_local.replace(hour=14, minute=0, second=0).isoformat()
    end_iso = now_local.replace(hour=14, minute=30, second=0).isoformat()
    storage.save_calendar_events("user_1", [{
        "id": "cal-today-1",
        "parent_uid": "cal-1",
        "title": "Quarterly Planning",
        "description": "",
        "location": "Zoom",
        "meeting_link": "https://zoom.us/j/12345",
        "start_time": start_iso,
        "end_time": end_iso,
        "is_recurring": 0,
        "event_md5": "md5-today"
    }])
    with patch("pithon.agent.briefing.fetch_news_headlines", return_value={"local": [], "national": [], "world": []}),          patch("pithon.agent.briefing.get_weather_report", return_value={"summary": "25C"}):
        briefing = generate_daily_briefing("user_1", storage, tz_name="Asia/Kolkata")
        assert "Today's Agenda & Calls" in briefing
        assert "Quarterly Planning" in briefing
        assert "https://zoom.us/j/12345" in briefing
