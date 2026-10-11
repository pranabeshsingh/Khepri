import pytest
from datetime import datetime, timezone
import zoneinfo
from pithon.agent.time_context import get_current_time_info, format_temporal_prompt_header

def test_get_current_time_info_default_kolkata():
    info = get_current_time_info("Asia/Kolkata")
    assert "year" in info
    assert "month" in info
    assert "day" in info
    assert "weekday" in info
    assert "time" in info
    assert "iso" in info
    assert info["timezone"] == "Asia/Kolkata"
    assert info["year"] >= 2026

def test_get_current_time_info_custom_tz():
    info = get_current_time_info("UTC")
    assert info["timezone"] == "UTC"

def test_format_temporal_prompt_header():
    header = format_temporal_prompt_header("Asia/Kolkata")
    assert "[Current Date & Time]" in header
    assert "Timezone: Asia/Kolkata" in header
    assert "Current Time:" in header
