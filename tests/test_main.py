from pathlib import Path
from PySide6.QtCore import Qt
from main import MainWindow


def test_main_window_creation(qapp):
    window = MainWindow()
    assert window.windowTitle() == "PDF Viewer"
    assert window.toolbar is not None
    assert window.search_bar is not None


def test_open_pdf(qapp, sample_pdf):
    window = MainWindow()
    window.open_file(sample_pdf)
    assert window.renderer.page_count == 1
    assert "sample.pdf" in window.windowTitle()
    window.close()


def test_title_shows_dirty_indicator(qapp, sample_pdf):
    window = MainWindow()
    window.open_file(sample_pdf)
    window._on_dirty_changed(True)
    assert window.windowTitle().startswith("*")
    window._on_dirty_changed(False)
    assert not window.windowTitle().startswith("*")
    window.close()


def test_keyboard_shortcuts_registered(qapp):
    window = MainWindow()
    assert window.toolbar.open_action.shortcut().toString() == "Ctrl+O"
    assert window.toolbar.save_action.shortcut().toString() == "Ctrl+S"
