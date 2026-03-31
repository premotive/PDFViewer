from PySide6.QtWidgets import QMainWindow
from toolbar import ToolBar


def test_toolbar_creation(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    window.addToolBar(toolbar)
    assert toolbar is not None


def test_toolbar_has_file_actions(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    assert toolbar.open_action is not None
    assert toolbar.save_action is not None
    assert toolbar.save_as_action is not None


def test_toolbar_has_theme_controls(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    assert toolbar.theme_combo is not None
    assert toolbar.bg_color_btn is not None
    assert toolbar.font_color_btn is not None


def test_toolbar_has_zoom_controls(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    assert toolbar.zoom_combo is not None


def test_toolbar_has_page_navigator(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    assert toolbar.page_spinbox is not None
    assert toolbar.page_total_label is not None


def test_toolbar_set_page_count(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    toolbar.set_page_count(42)
    assert toolbar.page_spinbox.maximum() == 42
    assert "42" in toolbar.page_total_label.text()


def test_toolbar_set_current_page(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    toolbar.set_page_count(10)
    toolbar.set_current_page(5)
    assert toolbar.page_spinbox.value() == 5


def test_save_disabled_when_clean(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    toolbar.set_dirty(False)
    assert not toolbar.save_action.isEnabled()


def test_save_enabled_when_dirty(qapp):
    window = QMainWindow()
    toolbar = ToolBar(window)
    toolbar.set_dirty(True)
    assert toolbar.save_action.isEnabled()
