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


def test_toolbar_has_hamburger(qtbot):
    toolbar = ToolBar()
    qtbot.addWidget(toolbar)
    assert toolbar.hamburger_btn is not None


def test_toolbar_hamburger_menu_has_actions(qtbot):
    toolbar = ToolBar()
    qtbot.addWidget(toolbar)
    menu = toolbar.hamburger_btn.menu()
    assert menu is not None
    action_texts = [a.text() for a in menu.actions() if a.text()]
    assert "Undo" in action_texts
    assert "Redo" in action_texts
    assert "Toggle Reading/Faithful Mode" in action_texts


def test_toolbar_no_page_navigator(qtbot):
    toolbar = ToolBar()
    qtbot.addWidget(toolbar)
    assert not hasattr(toolbar, 'page_spinbox')
