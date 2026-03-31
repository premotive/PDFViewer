import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Signal, QObject
from PySide6.QtGui import QColor
from tab_manager import TabState, TabManager


def test_tab_state_creation():
    state = TabState.__new__(TabState)
    state.file_path = None
    state.engine = MagicMock()
    state.renderer = MagicMock()
    state.edit_tracker = MagicMock()
    state.search_engine = MagicMock()
    state.undo_stack = MagicMock()
    assert state.file_path is None
    assert state.engine is not None


class _FakeTheme(QObject):
    """Minimal ThemeEngine stand-in that satisfies PageRenderer's requirements."""
    theme_changed = Signal()
    mode_changed = Signal()

    def __init__(self):
        super().__init__()
        self.bg_color = QColor("#FFFFFF")
        self.font_color = QColor("#000000")
        self.viewport_bg_color = QColor("#CCCCCC")
        self.show_tint = False
        self.show_text_overlays = False


@pytest.fixture
def mock_theme():
    return _FakeTheme()


def test_tab_manager_starts_empty(qtbot, mock_theme):
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    assert manager.count() == 0
    assert manager.active_tab() is None


def test_tab_manager_add_tab(qtbot, mock_theme):
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state = manager.add_tab("test.pdf")
    assert manager.count() == 1
    assert manager.active_tab() is state
    assert state.file_path is None


def test_tab_manager_remove_tab(qtbot, mock_theme):
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state1 = manager.add_tab("first.pdf")
    state2 = manager.add_tab("second.pdf")
    manager.remove_tab(0)
    assert manager.count() == 1
    assert manager.active_tab() is state2


def test_tab_manager_switch_tab(qtbot, mock_theme):
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state1 = manager.add_tab("first.pdf")
    state2 = manager.add_tab("second.pdf")
    manager.tab_bar.setCurrentIndex(0)
    assert manager.active_tab() is state1
