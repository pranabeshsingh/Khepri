"""Dynamic temporal grounding engine for timezone, date, and time awareness."""

from datetime import datetime
import zoneinfo
from typing import Dict, Any

def get_current_time_info(tz_name: str = "Asia/Kolkata") -> Dict[str, Any]:
    """Retrieve structured date and time metadata for a given timezone."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
        tz_name = "UTC"

    now = datetime.now(tz)
    return {
        "timezone": tz_name,
        "year": now.year,
        "month": now.strftime("%B"),
        "month_num": now.month,
        "day": now.day,
        "weekday": now.strftime("%A"),
        "time": now.strftime("%H:%M:%S"),
        "time_12h": now.strftime("%I:%M %p"),
        "iso": now.isoformat(),
        "utc_offset": now.strftime("%z")
    }

def format_temporal_prompt_header(tz_name: str = "Asia/Kolkata") -> str:
    """Generate a clean temporal header block to inject into system/user prompts."""
    info = get_current_time_info(tz_name)
    return (
        f"[Current Date & Time]\n"
        f"Current Time: {info['weekday']}, {info['day']} {info['month']} {info['year']}, {info['time']} ({info['time_12h']})\n"
        f"Timezone: {info['timezone']} (UTC{info['utc_offset'][:3]}:{info['utc_offset'][3:]})\n"
    )

def inject_temporal_context(prompt: str, tz_name: str = "Asia/Kolkata") -> str:
    """Prepend temporal context to a prompt."""
    header = format_temporal_prompt_header(tz_name)
    return f"{header}\n{prompt}"
