"""RFC 5545 iCalendar (ICS) parser, recurrence expander, and video meeting link detector.

Zero external dependencies: uses Python standard library only.
"""

from datetime import datetime, time, timedelta, timezone
import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
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

DAY_NAME_TO_WEEKDAY = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}


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

    # Fallback
    try:
        dt = datetime.strptime(clean_val[:8], "%Y%m%d")
        tz = zoneinfo.ZoneInfo(default_tz)
        return dt.replace(tzinfo=tz)
    except Exception:
        tz = zoneinfo.ZoneInfo(default_tz)
        return datetime.now(tz)


def _parse_line_property(line: str) -> Tuple[str, Dict[str, str], str]:
    """Parse a line into property name, parameters dict, and value."""
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
    
    If expand_window is provided, events (including recurring RRULE events)
    are filtered and expanded within (start_window, end_window).
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
            # EXDATE can contain comma-separated values
            for ex in value.split(","):
                ex_clean = ex.strip()
                if ex_clean:
                    exdates.append(ex_clean)
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

    title = _sanitize_title(summary)

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


def _parse_exdates(exdates: List[str], default_tz: str) -> Set[datetime]:
    """Parse list of EXDATE strings into datetime objects."""
    parsed: Set[datetime] = set()
    for ex in exdates:
        try:
            dt = _parse_ics_datetime(ex, {}, default_tz)
            parsed.add(dt)
        except Exception:
            continue
    return parsed


def expand_recurring_events(
    events: List[Dict[str, Any]],
    start_window: datetime,
    end_window: datetime,
    tz_name: str
) -> List[Dict[str, Any]]:
    """Expand recurring events (RRULE) and filter occurrences into sliding window.
    
    Each occurrence gets a composite id: f"{parent_uid}#{occ_start.isoformat()}".
    """
    expanded: List[Dict[str, Any]] = []

    for ev in events:
        rrule = ev.get("rrule")
        start_dt: datetime = ev["start_time"]
        end_dt: datetime = ev["end_time"]
        duration = end_dt - start_dt

        # Ensure start_window and end_window have comparable timezone info
        if start_dt.tzinfo is not None:
            if start_window.tzinfo is None:
                start_window = start_window.replace(tzinfo=start_dt.tzinfo)
            if end_window.tzinfo is None:
                end_window = end_window.replace(tzinfo=start_dt.tzinfo)
        else:
            if start_window.tzinfo is not None:
                start_window = start_window.astimezone(zoneinfo.ZoneInfo(tz_name)).replace(tzinfo=None)
            if end_window.tzinfo is not None:
                end_window = end_window.astimezone(zoneinfo.ZoneInfo(tz_name)).replace(tzinfo=None)

        if not rrule:
            # Single non-recurring event: include if it falls within or overlaps window
            if end_dt >= start_window and start_dt < end_window:
                ev_copy = dict(ev)
                ev_copy["id"] = ev["uid"]
                expanded.append(ev_copy)
            continue

        # Parse RRULE
        rrule_parts: Dict[str, str] = {}
        for part in rrule.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                rrule_parts[k.strip().upper()] = v.strip().upper()

        freq = rrule_parts.get("FREQ", "WEEKLY")
        interval = max(1, int(rrule_parts.get("INTERVAL", "1")))
        count = int(rrule_parts["COUNT"]) if "COUNT" in rrule_parts else None
        
        until_dt: Optional[datetime] = None
        if "UNTIL" in rrule_parts:
            try:
                until_dt = _parse_ics_datetime(rrule_parts["UNTIL"], {}, tz_name)
                if until_dt.tzinfo is not None and start_dt.tzinfo is not None:
                    until_dt = until_dt.astimezone(start_dt.tzinfo)
                elif until_dt.tzinfo is not None and start_dt.tzinfo is None:
                    until_dt = until_dt.replace(tzinfo=None)
            except Exception:
                until_dt = None

        byday_str = rrule_parts.get("BYDAY")
        bydays: Optional[List[int]] = None
        if byday_str:
            bydays = []
            for d in byday_str.split(","):
                # Day might have prefix e.g. 1MO or -1FR, strip digits
                d_clean = re.sub(r"[^A-Z]", "", d.strip())
                if d_clean in DAY_NAME_TO_WEEKDAY:
                    bydays.append(DAY_NAME_TO_WEEKDAY[d_clean])

        exdate_set = _parse_exdates(ev.get("exdates", []), tz_name)

        # Occurrence generator
        total_occurrences = 0
        max_loop_guard = 1000

        def _is_exdate(dt_to_check: datetime) -> bool:
            for ex in exdate_set:
                # Compare timestamps within 1 minute
                if abs((dt_to_check - ex).total_seconds()) < 60:
                    return True
                # Or compare dates if EXDATE was full day
                if dt_to_check.date() == ex.date() and ex.time() == time(0, 0):
                    return True
            return False

        if freq == "DAILY":
            curr = start_dt
            iterations = 0
            while iterations < max_loop_guard:
                iterations += 1
                if until_dt and curr > until_dt:
                    break
                if count is not None and total_occurrences >= count:
                    break
                total_occurrences += 1

                if not _is_exdate(curr):
                    curr_end = curr + duration
                    if curr_end >= start_window and curr < end_window:
                        occ = dict(ev)
                        occ["id"] = f"{ev['uid']}#{curr.isoformat()}"
                        occ["start_time"] = curr
                        occ["end_time"] = curr_end
                        expanded.append(occ)

                curr = curr + timedelta(days=interval)
                if curr >= end_window and (not until_dt or curr > until_dt):
                    break

        elif freq == "WEEKLY":
            # If BYDAY is specified, iterate by week
            curr_week_start = start_dt - timedelta(days=start_dt.weekday())
            iterations = 0

            days_to_check = sorted(bydays) if bydays is not None else [start_dt.weekday()]

            while iterations < max_loop_guard:
                iterations += 1
                week_all_past_window = True

                for weekday in days_to_check:
                    occ_date = curr_week_start + timedelta(days=weekday)
                    occ_dt = occ_date.replace(
                        hour=start_dt.hour,
                        minute=start_dt.minute,
                        second=start_dt.second,
                        microsecond=start_dt.microsecond
                    )

                    if occ_dt < start_dt:
                        continue
                    if until_dt and occ_dt > until_dt:
                        continue
                    if count is not None and total_occurrences >= count:
                        break

                    total_occurrences += 1

                    if occ_dt < end_window:
                        week_all_past_window = False

                    if not _is_exdate(occ_dt):
                        occ_end = occ_dt + duration
                        if occ_end >= start_window and occ_dt < end_window:
                            occ = dict(ev)
                            occ["id"] = f"{ev['uid']}#{occ_dt.isoformat()}"
                            occ["start_time"] = occ_dt
                            occ["end_time"] = occ_end
                            expanded.append(occ)

                if count is not None and total_occurrences >= count:
                    break
                if until_dt and curr_week_start > until_dt:
                    break
                if week_all_past_window and curr_week_start > end_window:
                    break

                curr_week_start = curr_week_start + timedelta(days=7 * interval)

        elif freq == "MONTHLY":
            curr = start_dt
            iterations = 0
            while iterations < max_loop_guard:
                iterations += 1
                if until_dt and curr > until_dt:
                    break
                if count is not None and total_occurrences >= count:
                    break
                total_occurrences += 1

                if not _is_exdate(curr):
                    curr_end = curr + duration
                    if curr_end >= start_window and curr < end_window:
                        occ = dict(ev)
                        occ["id"] = f"{ev['uid']}#{curr.isoformat()}"
                        occ["start_time"] = curr
                        occ["end_time"] = curr_end
                        expanded.append(occ)

                # Approximate month step: advance to same day next month
                new_month = curr.month + interval
                new_year = curr.year + (new_month - 1) // 12
                new_month = ((new_month - 1) % 12) + 1
                try:
                    curr = curr.replace(year=new_year, month=new_month)
                except ValueError:
                    # Day out of range (e.g. 31st), clamp to end of month
                    curr = curr.replace(year=new_year, month=new_month, day=28)

                if curr >= end_window:
                    break

        else:
            # Fallback for other frequencies: include base event if in window
            if end_dt >= start_window and start_dt < end_window:
                ev_copy = dict(ev)
                ev_copy["id"] = ev["uid"]
                expanded.append(ev_copy)

    # Sort expanded events by start_time
    expanded.sort(key=lambda x: x["start_time"])
    return expanded


def fetch_and_parse_calendar(
    url: str,
    current_feed_md5: str = "",
    tz_name: str = "Asia/Kolkata",
    expand_window: Optional[Tuple[datetime, datetime]] = None
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Fetch remote ICS calendar, compare MD5, and parse if modified.
    
    Returns:
        (changed: bool, feed_md5: str, events: List[Dict[str, Any]])
    """
    clean_url = url.strip()
    if clean_url.startswith("webcal://"):
        clean_url = "https://" + clean_url[9:]
    elif not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return False, current_feed_md5, []

    req = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "Khepri-Calendar-Sync/1.0 (RFC 5545 Client)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw_bytes = resp.read()
    except Exception as e:
        logger.error(f"Failed to fetch calendar from {clean_url}: {e}")
        return False, current_feed_md5, []

    new_feed_md5 = compute_md5(raw_bytes)
    if current_feed_md5 and new_feed_md5 == current_feed_md5:
        # Feed unchanged: 0ms overhead, skip full parsing
        return False, new_feed_md5, []

    # Decode text
    try:
        content_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_text = raw_bytes.decode("latin-1", errors="replace")

    if expand_window is None:
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        expand_window = (now - timedelta(days=1), now + timedelta(days=14))

    events = parse_ics_feed(content_text, default_tz=tz_name, expand_window=expand_window)
    return True, new_feed_md5, events

def handle_calendar_subcommand(
    text: str,
    storage: Any,
    chat_id: str,
    tz_name: str = "Asia/Kolkata"
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Execute a ``/calendar set|alert|sync`` subcommand.

    Returns ``(reply_text, tool_context)`` when the text was a recognised
    subcommand, or ``None`` when it is a bare ``/calendar``/``/agenda`` request
    and the caller should fall through to rendering the event list.

    Lives here rather than in the Telegram bot because the web portal needs the
    identical behaviour: both surfaces must share one implementation or they
    silently drift, which is how ``/calendar set <url>`` used to be swallowed
    by the portal's inline handler.
    """
    parts = text.strip().split()
    if not parts or not parts[0].lower().startswith(("/calendar", "/calender", "/agenda")):
        return None
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "set" and len(parts) > 2:
        cal_url = parts[2].strip()
        if not cal_url.startswith(("http://", "https://", "webcal://")):
            return (
                "⚠️ Invalid URL. Must begin with `https://`, `http://`, or `webcal://`.",
                {"type": "calendar", "ok": False},
            )
        if storage:
            storage.update_calendar_settings(chat_id, url=cal_url)
        _, feed_md5, events = fetch_and_parse_calendar(cal_url, "", tz_name)
        if storage:
            storage.save_calendar_events(chat_id, events)
            storage.update_calendar_settings(chat_id, feed_md5=feed_md5)
        return (
            f"✅ *Calendar URL configured and synced!*\n\n"
            f"🔗 *Feed URL:* `{cal_url}`\n"
            f"📥 *Meetings parsed:* `{len(events)}` upcoming events found.",
            {"type": "calendar", "configured": True, "events": len(events)},
        )

    if sub == "alert" and len(parts) > 2:
        try:
            mins = int(parts[2].strip())
            if mins < 1 or mins > 120:
                raise ValueError
        except ValueError:
            return (
                "⚠️ Please specify alert minutes between 1 and 120 (e.g. `/calendar alert 15`).",
                {"type": "calendar", "ok": False},
            )
        if storage:
            storage.update_calendar_settings(chat_id, alert_mins=mins)
        return (
            f"✅ *Meeting alert lead time updated to {mins} minutes before call.*",
            {"type": "calendar", "alert_mins": mins},
        )

    if sub == "sync":
        prof = storage.get_user_profile(chat_id) if storage else {}
        cal_url = prof.get("calendar_url") or os.environ.get("CALENDAR_ICS_URL", "")
        if not cal_url:
            return (
                "⚠️ No calendar URL configured yet. Use `/calendar set <url>` to configure.",
                {"type": "calendar", "ok": False},
            )
        _, feed_md5, events = fetch_and_parse_calendar(cal_url, "", tz_name)
        if storage:
            storage.save_calendar_events(chat_id, events)
            storage.update_calendar_settings(chat_id, feed_md5=feed_md5)
        return (
            f"🔄 *Calendar synced!* Found `{len(events)}` upcoming meetings.",
            {"type": "calendar", "synced": True, "events": len(events)},
        )

    return None


def is_calendar_intent(text: str) -> bool:
    """Detect if a user prompt is asking about their calendar, agenda, calls, or meetings."""
    if not text:
        return False
    t = text.lower().strip()
    if any(k in t for k in ("agenda", "calendar", "calender")):
        return True
    if any(k in t for k in ("meeting", "meetings", "calls", "schedule", "appointments")) and any(
        w in t for w in ("today", "tomorrow", "my", "upcoming", "have", "what", "next", "check", "any", "got")
    ):
        return True
    return False

