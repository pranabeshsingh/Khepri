"""Tests for Khepri /init user profile onboarding flow."""

import os
import shutil
import pytest
from pithon.agent.storage import Storage
from pithon.agent.profile import (
    start_onboarding,
    handle_onboarding_step,
    format_user_profile_prompt_header,
    get_default_weather_city
)


@pytest.fixture
def temp_storage(tmp_path):
    db_file = tmp_path / "test_pithon.db"
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    orig_notes = os.environ.get("NOTES_DIR")
    os.environ["NOTES_DIR"] = str(notes_dir)
    storage = Storage(str(db_file))
    yield storage
    if orig_notes:
        os.environ["NOTES_DIR"] = orig_notes
    else:
        os.environ.pop("NOTES_DIR", None)


def test_start_onboarding_wizard(temp_storage):
    msg = start_onboarding("test_chat_1", temp_storage)
    assert "Welcome to Khepri" in msg
    assert "What is your preferred name" in msg
    prof = temp_storage.get_user_profile("test_chat_1")
    assert prof is not None
    assert prof["step"] == "name"


def test_onboarding_lifecycle_steps(temp_storage):
    chat_id = "test_chat_2"
    start_onboarding(chat_id, temp_storage)

    # Step 1: Provide Name
    r1 = handle_onboarding_step(chat_id, "Devin", temp_storage)
    assert "Nice to meet you, *Devin*" in r1
    assert "What is your home city" in r1
    assert temp_storage.get_user_profile(chat_id)["step"] == "city"

    # Step 2: Provide City
    r2 = handle_onboarding_step(chat_id, "Munich", temp_storage)
    assert "Location set to *Munich*" in r2
    assert "When would you prefer your daily briefings" in r2
    assert temp_storage.get_user_profile(chat_id)["step"] == "digest"

    # Step 3: Provide Digest Preference
    r3 = handle_onboarding_step(chat_id, "Morning 8:00 AM", temp_storage)
    assert "Almost done" in r3
    assert "What is your primary work" in r3
    assert temp_storage.get_user_profile(chat_id)["step"] == "focus"

    # Step 4: Provide Primary Focus
    r4 = handle_onboarding_step(chat_id, "Autonomous Robotics", temp_storage)
    assert "Setup Complete" in r4
    assert "Devin" in r4
    assert "Munich" in r4
    assert "Autonomous Robotics" in r4

    # Profile in storage must be finalized and step cleared
    final_prof = temp_storage.get_user_profile(chat_id)
    assert final_prof["name"] == "Devin"
    assert final_prof["city"] == "Munich"
    assert final_prof["digest_pref"] == "Morning 8:00 AM"
    assert final_prof["focus"] == "Autonomous Robotics"
    assert final_prof["step"] is None

    # Context injection must format properly
    hdr = format_user_profile_prompt_header(temp_storage, chat_id)
    assert "[User Profile]" in hdr
    assert "Name: Devin" in hdr
    assert "Home Location: Munich" in hdr

    # Default weather city should resolve to Munich
    city = get_default_weather_city(temp_storage, chat_id)
    assert city == "Munich"


def test_fast_track_init(temp_storage):
    chat_id = "test_chat_fast"
    msg = start_onboarding(chat_id, temp_storage, "Aria | Seattle | Evening 9pm | AI Safety")
    assert "Setup Complete" in msg
    assert "Aria" in msg
    assert "Seattle" in msg

    prof = temp_storage.get_user_profile(chat_id)
    assert prof["name"] == "Aria"
    assert prof["city"] == "Seattle"
    assert prof["digest_pref"] == "Evening 9pm"
    assert prof["focus"] == "AI Safety"
    assert prof["step"] is None


def test_cancel_onboarding(temp_storage):
    chat_id = "test_chat_cancel"
    start_onboarding(chat_id, temp_storage)
    assert temp_storage.get_user_profile(chat_id)["step"] == "name"

    r = handle_onboarding_step(chat_id, "/cancel", temp_storage)
    assert "Setup cancelled" in r
    assert temp_storage.get_user_profile(chat_id)["step"] is None
