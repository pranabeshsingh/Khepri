"""Unit tests for RFC 5545 calendar parsing, link detection, and recurrence."""

from datetime import datetime, timezone, timedelta
from io import BytesIO
from unittest.mock import patch, MagicMock
import zoneinfo
import pytest

from pithon.agent.calendar import (
    parse_ics_feed,
    extract_video_meeting_link,
    compute_md5,
    unfold_ics_lines,
    expand_recurring_events,
    fetch_and_parse_calendar,
)


def test_extract_video_meeting_link():
    assert extract_video_meeting_link("Join via https://meet.google.com/abc-defg-hij") == "https://meet.google.com/abc-defg-hij"
    assert extract_video_meeting_link("Zoom link: https://us02web.zoom.us/j/123456789?pwd=xyz") == "https://us02web.zoom.us/j/123456789?pwd=xyz"
    assert extract_video_meeting_link("Teams: https://teams.microsoft.com/l/meetup-join/19%3ameeting") == "https://teams.microsoft.com/l/meetup-join/19%3ameeting"
    assert extract_video_meeting_link("Conference Room B (No link)") is None


def test_unfold_ics_lines():
    # RFC 5545: fold marker is 1 space/tab; text spaces are preserved after the marker
    folded = "DESCRIPTION:This is a very long line\r\n  that has been folded\r\n\t by the server.\r\nSUMMARY:Test"
    unfolded = unfold_ics_lines(folded)
    assert len(unfolded) == 2
    assert unfolded[0] == "DESCRIPTION:This is a very long line that has been folded by the server."
    assert unfolded[1] == "SUMMARY:Test"


def test_parse_single_event_ics():
    raw_ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:meeting-001@example.com\r\n"
        "SUMMARY:Architecture Sync [Core]\r\n"
        "DESCRIPTION:Discussion on cgroups.\\nJoin: https://meet.google.com/abc-defg-hij\r\n"
        "LOCATION:Google Meet\r\n"
        "DTSTART:20261013T090000Z\r\n"
        "DTEND:20261013T093000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = parse_ics_feed(raw_ics, default_tz="Asia/Kolkata")
    assert len(events) == 1
    ev = events[0]
    assert ev["uid"] == "meeting-001@example.com"
    assert ev["title"] == "Architecture Sync (Core)"
    assert ev["meeting_link"] == "https://meet.google.com/abc-defg-hij"
    assert ev["start_time"].tzinfo is not None
    assert ev["event_md5"] is not None


def test_rrule_weekly_expansion():
    raw_ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:daily-standup@company.com\r\n"
        "SUMMARY:Daily Standup\r\n"
        "DTSTART;TZID=Asia/Kolkata:20261012T100000\r\n"
        "DTEND;TZID=Asia/Kolkata:20261012T103000\r\n"
        "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261030T235959Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    # Expand across 7 days: Monday 2026-10-12 to Monday 2026-10-19
    start_w = datetime(2026, 10, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
    end_w = datetime(2026, 10, 19, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
    events = parse_ics_feed(raw_ics, default_tz="Asia/Kolkata", expand_window=(start_w, end_w))
    # Monday to Friday = 5 occurrences
    assert len(events) == 5
    uids = [e["id"] for e in events]
    assert len(set(uids)) == 5
    assert uids[0].startswith("daily-standup@company.com#")
    for ev in events:
        assert ev["parent_uid"] == "daily-standup@company.com"
        assert (ev["end_time"] - ev["start_time"]) == timedelta(minutes=30)


def test_rrule_daily_and_exdate():
    raw_ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:daily-sync@company.com\r\n"
        "SUMMARY:Daily Check-in\r\n"
        "DTSTART:20261010T090000Z\r\n"
        "DTEND:20261010T091500Z\r\n"
        "RRULE:FREQ=DAILY;COUNT=5\r\n"
        "EXDATE:20261012T090000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    start_w = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
    end_w = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)
    events = parse_ics_feed(raw_ics, default_tz="UTC", expand_window=(start_w, end_w))
    # 5 count minus 1 exdate = 4 occurrences (Oct 10, 11, 13, 14)
    assert len(events) == 4
    days = [e["start_time"].day for e in events]
    assert days == [10, 11, 13, 14]


def test_fetch_and_parse_calendar_caching():
    sample_ics = (
        b"BEGIN:VCALENDAR\r\n"
        b"VERSION:2.0\r\n"
        b"BEGIN:VEVENT\r\n"
        b"UID:one-off@example.com\r\n"
        b"SUMMARY:Client Review\r\n"
        b"DTSTART:20261013T140000Z\r\n"
        b"DTEND:20261013T143000Z\r\n"
        b"END:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_ics
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        # First fetch: webcal converted to https
        changed, feed_md5, events = fetch_and_parse_calendar("webcal://example.com/cal.ics", current_feed_md5="", tz_name="UTC")
        assert changed is True
        assert len(events) == 1
        assert feed_md5 == compute_md5(sample_ics)
        assert mock_urlopen.call_args[0][0].full_url == "https://example.com/cal.ics"

        # Second fetch with identical MD5: should return changed=False, events=[] without parsing
        changed_again, same_md5, empty_events = fetch_and_parse_calendar("https://example.com/cal.ics", current_feed_md5=feed_md5, tz_name="UTC")
        assert changed_again is False
        assert same_md5 == feed_md5
        assert empty_events == []
