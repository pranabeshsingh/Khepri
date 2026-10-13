"""RFC 5545 iCalendar (ICS) parser, recurrence expander, and video meeting link detector.

Zero external dependencies: uses Python standard library only.
"""

from datetime import datetime, date, time, timedelta, timezone
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.request
import zoneinfo

logger = logging.getLogger(__name__)

# Regex patterns for video meeting links
MEETING_PATTERNS = [
    re.compile(r"https?://meet\.google\.com/[a-z0-9\-]+", re.IGNORECASE),
    re.compile(r"https?://[a-z0-9\.\-]*zoom\.us/j/[0-9]+(?:\?[^\s\"'<>]*)?", re.IGNORECASE),
    re.compile(r"https?://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+", re.IGNORECASE),
    re.compile(r"https?://[a-z0-9\.\-]*webex\.com/[^\s\"'<>]+", re.IGNORECASE),
]


def compute_md5(data: Union[str, bytes]) -> str:
    """Compute MD5 hex digest for string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.md5(data).hexdigest()


def extract_video_meeting_link(text: Optional[str]) -> Optional[str]:
    """Extract Google Meet, Zoom, Teams, or Webex video call URL from text."""
    if not text:
        return None
    for pattern in MEETING_PATTERNS:
        match = pattern.search(text)
        if match:
            url = match.group(0).rstrip(".,;)>]")
            return url
    return None


def unfold_ics_lines(raw_text: str) -> List[str]:
    """Unfold lines per RFC 5545 section 3.1.
    
    Lines that begin with space or tab are continuation of previous line.
    """
    raw_lines = raw_text.splitlines()
    unfolded: List[str] = []
    for line in raw_lines:
        if not line:
            continue
        if (line.startswith(" ") or line.startswith("\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _unescape_ics_text(val: str) -> str:
    """Unescape RFC 5545 escaped characters."""
    val = val.replace(r"\n", "\n").replace(r"\N", "\n")
    val = val.replace(r"\,", ",").replace(r"\;", ";").replace(r"\\", "\\")
    return val


def _sanitize_title(title: str) -> str:
    """Sanitize title to prevent Telegram markdown parsing errors."""
    if not title:
        return "Untitled Event"
    # Replace square brackets to avoid Telegram markdown link parsing bugs
    sanitized = title.replace("[", "(").replace("]", ")")
    # Clean control characters except space
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", sanitized)
    return sanitized.strip() or "Untitled Event"


def _parse_ics_datetime(value_str: str, params: Dict[str, str], default_tz: str) -> datetime:
    """Parse ICS datetime or date value according to RFC 5545."""
    clean_val = value_str.strip()
    
    # Check for DATE format: YYYYMMDD
    if len(clean_val) == 8 and clean_val.isdigit():
        year = int(clean_val[0:4])
        month = int(clean_val[4:6])
        day = int(clean_val[6:8])
        tz = zoneinfo.ZoneInfo(default_tz)
        return datetime(year, month, day, 0, 0, 0, tzinfo=tz)

    # UTC datetime: YYYYMMDDTHHMMSSZ
    if clean_val.endswith("Z"):
        dt_str = clean_val[:-1]
        dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=timezone.utc)

    # Local datetime: YYYYMMDDTHHMMSS
    if "T" in clean_val:
        # Check params for TZID
        tzid = params.get("TZID")
        if tzid:
            try:
                tz = zoneinfo.ZoneInfo(tzid)
            except Exception:
                tz = zoneinfo.ZoneInfo(default_tz)
        else:
            tz = zoneinfo.ZoneInfo(default_tz)
        dt = datetime.strptime(clean_val, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=tz)

    # Fallback to date
    try:
        dt = datetime.strptime(clean_val[:8], "%Y%m%d")
        tz = zoneinfo.ZoneInfo(default_tz)
        return dt.replace(tzinfo=tz)
    except Exception:
        tz = zoneinfo.ZoneInfo(default_tz)
        return datetime.now(tz)


def _parse_line_property(line: str) -> Tuple[str, Dict[str, str], str]:
    """Parse a line into property name, parameters dict, and value.
    
    Example: 'DTSTART;TZID=Asia/Kolkata:20261012T100000' ->
             ('DTSTART', {'TZID': 'Asia/Kolkata'}, '20261012T100000')
    """
    if ":" not in line:
        return line.upper(), {}, ""
    name_and_params, value = line.split(":", 1)
    parts = name_and_params.split(";")
    prop_name = parts[0].strip().upper()
    params: Dict[str, str] = {}
    for param in parts[1:]:
        if "=" in param:
            k, v = param.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return prop_name, params, value


def parse_ics_feed(
    ics_content: str,
    default_tz: str = "Asia/Kolkata",
    expand_window: Optional[Tuple[datetime, datetime]] = None
) -> List[Dict[str, Any]]:
    """Parse raw ICS content into a list of event dictionaries.
    
    If expand_window is provided and events contain RRULE, recurring instances
    are expanded within that window.
    """
    lines = unfold_ics_lines(ics_content)
    events: List[Dict[str, Any]] = []
    
    in_vevent = False
    current_lines: List[str] = []
    
    for line in lines:
        upper_line = line.strip().upper()
        if upper_line == "BEGIN:VEVENT":
            in_vevent = True
            current_lines = [line]
            continue
        elif upper_line == "END:VEVENT":
            if in_vevent:
                current_lines.append(line)
                ev = _parse_vevent_block(current_lines, default_tz)
                if ev:
                    events.append(ev)
            in_vevent = False
            current_lines = []
            continue
        
        if in_vevent:
            current_lines.append(line)

    if expand_window:
        events = expand_recurring_events(events, expand_window[0], expand_window[1], default_tz)

    return events


def _parse_vevent_block(lines: List[str], default_tz: str) -> Optional[Dict[str, Any]]:
    """Parse raw lines of a single VEVENT block."""
    raw_block = "\r\n".join(lines)
    event_md5 = compute_md5(raw_block)
    
    uid = ""
    summary = ""
    description = ""
    location = ""
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    rrule: Optional[str] = None
    exdates: List[str] = []
    status = "CONFIRMED"
    
    for line in lines:
        prop_name, params, value = _parse_line_property(line)
        if prop_name == "UID":
            uid = value.strip()
        elif prop_name == "SUMMARY":
            summary = _unescape_ics_text(value)
        elif prop_name == "DESCRIPTION":
            description = _unescape_ics_text(value)
        elif prop_name == "LOCATION":
            location = _unescape_ics_text(value)
        elif prop_name == "DTSTART":
            start_dt = _parse_ics_datetime(value, params, default_tz)
        elif prop_name == "DTEND":
            end_dt = _parse_ics_datetime(value, params, default_tz)
        elif prop_name == "RRULE":
            rrule = value.strip()
        elif prop_name == "EXDATE":
            exdates.append(value.strip())
        elif prop_name == "STATUS":
            status = value.strip().upper()

    if status == "CANCELLED":
        return None

    if not uid:
        uid = f"event-{event_md5[:12]}"

    if not start_dt:
        tz = zoneinfo.ZoneInfo(default_tz)
        start_dt = datetime.now(tz)
    
    if not end_dt:
        end_dt = start_dt + timedelta(minutes=30)
    elif end_dt < start_dt:
        end_dt = start_dt + timedelta(minutes=30)

    # Sanitize title
    title = _sanitize_title(summary)

    # Extract video meeting link from location, description, or anywhere in block
    meeting_link = extract_video_meeting_link(location) or extract_video_meeting_link(description)
    if not meeting_link:
        meeting_link = extract_video_meeting_link(raw_block)

    return {
        "id": uid,
        "uid": uid,
        "parent_uid": uid,
        "title": title,
        "description": description,
        "location": location,
        "meeting_link": meeting_link,
        "start_time": start_dt,
        "end_time": end_dt,
        "is_recurring": 1 if rrule else 0,
        "rrule": rrule,
        "exdates": exdates,
        "event_md5": event_md5,
    }


def expand_recurring_events(
    events: List[Dict[str, Any]],
    start_window: datetime,
    end_window: datetime,
    tz_name: str
) -> List[Dict[str, Any]]:
    """Placeholder for Task 2 expansion - will be implemented in Task 2."""
    expanded: List[Dict[str, Any]] = []
    for ev in events:
        expanded.append(ev)
    return expanded
