import os
import pytest
from pithon.agent.markdown_store import (
    parse_frontmatter,
    dump_frontmatter,
    ProfileStore,
    TasksStore,
    BriefingStore
)

def test_frontmatter_roundtrip():
    meta = {
        "name": "Pranabesh",
        "city": "Kolkata",
        "alert_mins": 10,
        "is_active": True,
        "calendar_url": "https://example.com/cal.ics"
    }
    body = "# Custom Persona\nPrefers concise responses."
    dumped = dump_frontmatter(meta, body)
    parsed_meta, parsed_body = parse_frontmatter(dumped)

    assert parsed_meta["name"] == "Pranabesh"
    assert parsed_meta["city"] == "Kolkata"
    assert parsed_meta["alert_mins"] == 10
    assert parsed_meta["is_active"] is True
    assert parsed_meta["calendar_url"] == "https://example.com/cal.ics"
    assert "Custom Persona" in parsed_body

def test_profile_store(tmp_path):
    store = ProfileStore(data_dir=str(tmp_path))
    assert not os.path.exists(store.filepath)

    store.save_profile({"name": "Pranabesh", "city": "Kolkata"}, body="Custom body")
    assert os.path.exists(store.filepath)

    meta, body = store.load_profile()
    assert meta["name"] == "Pranabesh"
    assert meta["city"] == "Kolkata"
    assert "Custom body" in body

    # Update single field
    store.save_profile({"digest_pref": "09:00"})
    meta2, body2 = store.load_profile()
    assert meta2["name"] == "Pranabesh"
    assert meta2["digest_pref"] == "09:00"
    assert "Custom body" in body2

def test_tasks_store_sync(tmp_path):
    store = TasksStore(data_dir=str(tmp_path))
    sample_tasks = [
        {"id": 1, "title": "Deploy v0.2 to VPS", "is_completed": 0, "list_name": "default", "due_at": "2026-10-15T18:00:00"},
        {"id": 2, "title": "Buy groceries", "is_completed": 0, "list_name": "home", "due_at": None},
        {"id": 3, "title": "Setup server", "is_completed": 1, "list_name": "work", "due_at": None}
    ]

    store.sync_from_tasks(sample_tasks)
    assert os.path.exists(store.filepath)

    loaded = store.load_tasks()
    assert len(loaded) == 3
    assert loaded[0]["title"] == "Deploy v0.2 to VPS"
    assert loaded[0]["id"] == 1
    assert loaded[0]["is_completed"] == 0
    assert loaded[1]["list_name"] == "home"
    assert loaded[2]["is_completed"] == 1

def test_briefing_store(tmp_path):
    store = BriefingStore(data_dir=str(tmp_path))
    briefing_text = "📰 Daily Briefing: All systems nominal."
    path = store.save_briefing(briefing_text, date_str="2026-10-14")

    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "All systems nominal" in content
