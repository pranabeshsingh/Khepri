import pytest
from pithon.agent.memory import save_note, search_notes, list_notes, get_note_content, delete_note

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

    # 6. Delete
    deleted = delete_note("server-credentials.md", base_dir=notes_dir)
    assert deleted is True
    assert get_note_content("server-credentials.md", base_dir=notes_dir) is None
    assert len(list_notes(base_dir=notes_dir)) == 0


def test_path_traversal_prevention(tmp_path):
    notes_dir = str(tmp_path / "notes")
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("SUPER_SECRET")

    # Path traversal via .. or absolute path should be rejected or contained strictly within notes_dir
    res = save_note("../../../evil", "evil content", base_dir=notes_dir)
    # The note should be safely contained inside notes_dir
    assert res["success"] is True
    assert ".." not in res["filename"]
    assert res["path"].startswith(notes_dir)

    # Attempting to read outside notes_dir
    assert get_note_content(f"../../{secret_file.name}", base_dir=notes_dir) is None
    assert get_note_content("/etc/passwd", base_dir=notes_dir) is None

    # Attempting to delete outside notes_dir
    assert delete_note(f"../../{secret_file.name}", base_dir=notes_dir) is False
    assert secret_file.exists()
    assert secret_file.read_text() == "SUPER_SECRET"
