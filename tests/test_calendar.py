"""Unit tests for RFC 5545 calendar parsing, link detection, and recurrence."""

from datetime import datetime
import zoneinfo
import pytest

from pithon.agent.calendar import (
    parse_ics_feed,
    extract_video_meeting_link,
    compute_md5,
    unfold_ics_lines
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
