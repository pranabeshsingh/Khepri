import pytest
from pithon.presets import get_preset_system_prompt, PRESETS

def test_available_presets():
    assert "log-analyzer" in PRESETS
    assert "reminder" in PRESETS
    assert "weather" in PRESETS
    assert "default" in PRESETS

def test_get_preset_system_prompt():
    prompt = get_preset_system_prompt("log-analyzer")
    assert "log" in prompt.lower()
    assert "root cause" in prompt.lower()

    reminder = get_preset_system_prompt("reminder")
    assert "json" in reminder.lower()

    weather = get_preset_system_prompt("weather")
    assert "weather" in weather.lower()

def test_unknown_preset_fallback():
    prompt = get_preset_system_prompt("nonexistent")
    assert prompt == PRESETS["default"]
