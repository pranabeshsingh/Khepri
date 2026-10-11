import pytest
from pithon.agent.memory import save_note, search_notes, list_notes, get_note_content

def test_memory_lifecycle(tmp_path):
    notes_dir = str(tmp_path / "notes")

    # 1. Save new note
    res = save_note("Server Credentials", "IP is 10.0.0.1 user ubuntu", tags="dev,ssh", base_dir=notes_dir)
    assert res["success"] is True
    assert res["filename"] == "server-credentials.md"
    assert res["updated"] is False

    # 2. Get exact content
    content = get_note_content("server-credentials", base_dir=notes_dir)
    assert "IP is 10.0.0.1" in content
    assert "Tags" in content

    # 3. Update existing note
    res_up = save_note("Server Credentials", "Added port 2222", base_dir=notes_dir)
    assert res_up["updated"] is True
    updated_content = get_note_content("server-credentials", base_dir=notes_dir)
    assert "Update:" in updated_content
    assert "Added port 2222" in updated_content

    # 4. Search
    found = search_notes("10.0.0.1", base_dir=notes_dir)
    assert len(found) == 1
    assert "Server Credentials" in found[0]["title"]

    # 5. List
    notes = list_notes(base_dir=notes_dir)
    assert len(notes) == 1
    assert notes[0]["filename"] == "server-credentials.md"
