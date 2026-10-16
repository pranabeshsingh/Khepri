"""Regression tests: the notes store must follow DB_PATH, not $CWD/data/notes.

Previously every production call site invoked the memory helpers without a
base_dir, so notes always resolved to the relative 'data/notes' regardless of
DB_PATH. Pointing DB_PATH at a temp dir therefore still read and wrote the real
repository notes.
"""

import os

import pytest

from pithon.agent.memory import save_note, list_notes, search_notes
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

    assert os.listdir(storage.notes_dir()) == ["isolated.md"]
    assert list_notes(base_dir=str(cwd_notes)) == []
    assert search_notes("scoped", base_dir=str(cwd_notes)) == []
