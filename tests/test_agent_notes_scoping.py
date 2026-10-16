"""Regression tests: the notes store must follow DB_PATH, not $CWD/data/notes.

Previously every production call site invoked the memory helpers without a
base_dir, so notes always resolved to the relative 'data/notes' regardless of
DB_PATH. Pointing DB_PATH at a temp dir therefore still read and wrote the real
repository notes.
"""

import os

import pytest

from pithon.agent.memory import save_note, list_notes, search_notes, seed_notes
from pithon.agent.storage import Storage


def test_notes_dir_is_colocated_with_db(tmp_path):
    storage = Storage(str(tmp_path / "notes_scope.db"))
    assert storage.notes_dir() == os.path.join(str(tmp_path), "notes")


def test_default_db_path_keeps_default_notes_location(tmp_path, monkeypatch):
    """With the shipped default, notes_dir() must resolve to memory.DEFAULT_NOTES_DIR.

    Storage stores an absolute data_dir, so compare resolved paths rather than
    strings. This is the backward-compatibility guarantee: existing installs
    using the default DB_PATH keep reading and writing ./data/notes.
    """
    from pithon.agent.memory import DEFAULT_NOTES_DIR

    monkeypatch.chdir(tmp_path)
    storage = Storage("data/pithon.db")

    assert os.path.realpath(storage.notes_dir()) == os.path.realpath(DEFAULT_NOTES_DIR)


def test_notes_are_isolated_from_cwd_data_notes(tmp_path, monkeypatch):
    """Writing a note through a temp Storage must not touch ./data/notes."""
    cwd_notes = tmp_path / "cwd" / "data" / "notes"
    cwd_notes.mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "cwd")

    storage = Storage(str(tmp_path / "iso" / "pithon.db"))
    save_note("isolated", "scoped content", base_dir=storage.notes_dir())

    assert "isolated.md" in os.listdir(storage.notes_dir())
    assert list_notes(base_dir=str(cwd_notes)) == []
    assert search_notes("scoped", base_dir=str(cwd_notes)) == []


def test_first_run_seeds_starter_notes(tmp_path):
    """A fresh install gets a starter system-specs note, because data/ is gitignored."""
    storage = Storage(str(tmp_path / "seed.db"))

    seeded = storage.notes_dir()
    assert os.path.isfile(os.path.join(seeded, "system-specs.md"))
    body = open(os.path.join(seeded, "system-specs.md"), encoding="utf-8").read()
    # cgroup figures must mirror docker-compose.yml
    assert "1408M RAM" in body
    assert "512M RAM" in body


def test_seeding_never_overwrites_an_existing_vault(tmp_path):
    """An existing vault, and a deliberately deleted starter, are both respected."""
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "my-note.md").write_text("mine", encoding="utf-8")

    assert seed_notes(str(notes)) == []
    assert not (notes / "system-specs.md").exists()

    # Deleting a starter note must not resurrect it on the next run.
    assert seed_notes(str(notes)) == []
    assert os.listdir(notes) == ["my-note.md"]


def test_seed_is_idempotent_on_repeated_storage_construction(tmp_path):
    Storage(str(tmp_path / "a.db"))
    Storage(str(tmp_path / "b.db"))
    assert os.listdir(tmp_path / "notes") == ["system-specs.md"]


def test_seeded_note_does_not_leak_into_cwd_notes(tmp_path, monkeypatch):
    """Seeding must respect the Storage's notes dir, not $CWD/data/notes."""
    monkeypatch.chdir(tmp_path)
    Storage(str(tmp_path / "iso" / "pithon.db"))

    assert os.path.isfile(str(tmp_path / "iso" / "notes" / "system-specs.md"))
    assert not os.path.isdir(str(tmp_path / "data"))
