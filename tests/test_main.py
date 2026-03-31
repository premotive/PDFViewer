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


def test_block_edit_mode_available(qapp, paragraph_pdf):
    """Verify the block editing infrastructure is wired up correctly."""
    window = MainWindow()
    window.open_file(paragraph_pdf)
    # The engine should be able to extract blocks
    blocks = window._main_engine.extract_blocks(0)
    assert len(blocks) >= 2
    # First block should have text
    assert blocks[0]["text"].strip() != ""
    # Max rect should be computable
    max_rect = window._main_engine.compute_max_block_rect(0, blocks[0]["block_num"])
    assert max_rect is not None
    assert max_rect[3] > blocks[0]["bbox"][3]  # extended past original bottom
    window.close()


def test_edit_tracker_block_dirty_indicator(qapp, paragraph_pdf):
    window = MainWindow()
    window.open_file(paragraph_pdf)
    assert not window._edit_tracker.is_dirty
    blocks = window._main_engine.extract_blocks(0)
    block = blocks[0]
    max_rect = window._main_engine.compute_max_block_rect(0, block["block_num"])
    window._edit_tracker.record_block_edit(
        page_num=0, block_num=block["block_num"],
        original_text=block["text"], new_text="Totally new text",
        block_bbox=block["bbox"], extended_bbox=max_rect,
        font=block["dominant_font"], size=block["dominant_size"],
        color=block["dominant_color"], flags=block["dominant_flags"], align=0,
    )
    assert window._edit_tracker.is_dirty
    window.close()
