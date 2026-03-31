import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from library_sidebar import LibraryData, LibraryEntry, LibrarySidebar


def test_library_entry_creation():
    entry = LibraryEntry(
        file_path="/test/doc.pdf",
        filename="doc.pdf",
        page_count=5,
        last_opened="2026-03-31T12:00:00",
        thumb_path="",
    )
    assert entry.filename == "doc.pdf"
    assert entry.page_count == 5


def test_library_data_add_entry(tmp_path):
    lib_path = tmp_path / "library.json"
    data = LibraryData(lib_path)
    data.add_or_update("/test/doc.pdf", "doc.pdf", 5)
    assert len(data.entries) == 1
    assert data.entries[0].filename == "doc.pdf"


def test_library_data_duplicate_updates(tmp_path):
    lib_path = tmp_path / "library.json"
    data = LibraryData(lib_path)
    data.add_or_update("/test/doc.pdf", "doc.pdf", 5)
    data.add_or_update("/test/doc.pdf", "doc.pdf", 5)
    assert len(data.entries) == 1


def test_library_data_save_and_load(tmp_path):
    lib_path = tmp_path / "library.json"
    data = LibraryData(lib_path)
    data.add_or_update("/test/doc.pdf", "doc.pdf", 5)
    data.save()
    assert lib_path.exists()
    data2 = LibraryData(lib_path)
    data2.load()
    assert len(data2.entries) == 1
    assert data2.entries[0].filename == "doc.pdf"


def test_library_data_remove_entry(tmp_path):
    lib_path = tmp_path / "library.json"
    data = LibraryData(lib_path)
    data.add_or_update("/test/doc.pdf", "doc.pdf", 5)
    data.remove("/test/doc.pdf")
    assert len(data.entries) == 0


def test_library_data_sorted_by_recent(tmp_path):
    lib_path = tmp_path / "library.json"
    data = LibraryData(lib_path)
    data.add_or_update("/test/old.pdf", "old.pdf", 3)
    data.add_or_update("/test/new.pdf", "new.pdf", 7)
    assert data.entries[0].filename == "new.pdf"


def test_library_sidebar_creation(qtbot):
    sidebar = LibrarySidebar()
    qtbot.addWidget(sidebar)
    assert sidebar.is_collapsed() is False


def test_library_sidebar_toggle(qtbot):
    sidebar = LibrarySidebar()
    qtbot.addWidget(sidebar)
    sidebar.toggle_collapsed()
    assert sidebar.is_collapsed() is True
    sidebar.toggle_collapsed()
    assert sidebar.is_collapsed() is False
