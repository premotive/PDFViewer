"""TabState and TabManager for multi-tab PDF viewing."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar, QStackedWidget, QVBoxLayout, QWidget
from PySide6.QtGui import QUndoStack

from pdf_engine import PDFEngine
from page_renderer import PageRenderer
from text_overlay import SelectionManager
from editor import EditTracker
from search import SearchEngine
from theme_engine import ThemeEngine

_PLUS_LABEL = "+"


class TabState:
    """Holds all per-document state for a single tab."""

    def __init__(self, theme_engine: ThemeEngine, parent_widget: QWidget | None = None):
        self.file_path: Path | None = None
        self.engine = PDFEngine()
        self.renderer = PageRenderer(main_engine=self.engine, theme_engine=theme_engine)
        self.edit_tracker = EditTracker()
        self.undo_stack = QUndoStack(parent_widget)
        self.search_engine = SearchEngine()
        self.selection_manager: SelectionManager | None = None
        self.active_edit = None
        self.search_results: list = []
        self.search_index: int = -1
        self.search_highlights: list = []
        self.current_highlight = None

        self.init_selection_manager()

    def init_selection_manager(self):
        """Create SelectionManager from renderer scene and overlay_manager."""
        self.selection_manager = SelectionManager(
            scene=self.renderer.scene,
            overlay_manager=self.renderer.overlay_manager,
        )

    def close(self):
        """Close renderer (stops worker) and engine."""
        self.renderer.close_document()
        self.engine.close()


class TabManager(QWidget):
    """Manages a QTabBar + QStackedWidget for multi-tab document viewing."""

    tab_changed = Signal(int)
    tab_close_requested = Signal(int)
    new_tab_requested = Signal()

    def __init__(self, theme_engine: ThemeEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self._theme_engine = theme_engine
        self._states: list[TabState] = []

        # Tab bar: closable, not movable, not expanding
        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)

        # Add the permanent "+" tab
        self.tab_bar.addTab(_PLUS_LABEL)
        self._plus_index = 0  # only tab right now
        self.tab_bar.setTabButton(self._plus_index, QTabBar.ButtonPosition.RightSide, None)

        # Stacked widget for renderer views
        self._stack = QStackedWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_bar)
        layout.addWidget(self._stack)

        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_close_requested)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Number of document tabs (excluding the + button tab)."""
        return len(self._states)

    def active_tab(self) -> TabState | None:
        """Return the TabState for the currently visible tab, or None."""
        idx = self.tab_bar.currentIndex()
        if idx < 0 or idx >= len(self._states):
            return None
        return self._states[idx]

    def tab_at(self, index: int) -> TabState | None:
        """Return TabState at the given index, or None if out of range."""
        if 0 <= index < len(self._states):
            return self._states[index]
        return None

    def add_tab(self, label: str) -> TabState:
        """Create a new TabState, insert a tab before +, switch to it."""
        state = TabState(theme_engine=self._theme_engine, parent_widget=self)
        insert_pos = len(self._states)  # right before the + tab

        # Insert tab into bar before the + tab
        self.tab_bar.insertTab(insert_pos, label)
        # The + tab index shifts by 1
        self._plus_index = insert_pos + 1
        # Make the new tab non-closable? No — keep closable. Remove close btn
        # from + tab in case it shifted.
        self._refresh_plus_tab()

        # Add renderer view to stack
        self._stack.insertWidget(insert_pos, state.renderer.view)
        self._states.insert(insert_pos, state)

        # Switch to the new tab
        self.tab_bar.setCurrentIndex(insert_pos)
        self._stack.setCurrentIndex(insert_pos)

        return state

    def remove_tab(self, index: int):
        """Remove tab at index and clean up its state."""
        if index < 0 or index >= len(self._states):
            return

        state = self._states.pop(index)
        state.close()

        # Remove from stack and bar
        widget = self._stack.widget(index)
        self._stack.removeWidget(widget)
        self.tab_bar.removeTab(index)

        # Update + tab index
        self._plus_index = len(self._states)
        self._refresh_plus_tab()

    def update_tab_label(self, index: int, label: str):
        """Update the label of the tab at index."""
        if 0 <= index < len(self._states):
            self.tab_bar.setTabText(index, label)

    def index_of_path(self, path: Path) -> int:
        """Return the tab index whose file_path matches, or -1."""
        for i, state in enumerate(self._states):
            if state.file_path == path:
                return i
        return -1

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_plus_tab(self):
        """Ensure the + tab has no close button."""
        plus_idx = self._plus_index
        if 0 <= plus_idx < self.tab_bar.count():
            self.tab_bar.setTabButton(plus_idx, QTabBar.ButtonPosition.RightSide, None)
            self.tab_bar.setTabButton(plus_idx, QTabBar.ButtonPosition.LeftSide, None)

    def _on_tab_changed(self, index: int):
        """Handle tab bar selection changes."""
        if index < 0:
            return
        if index == self._plus_index:
            # Revert to previous valid tab if there are any
            if self._states:
                prev = min(index - 1, len(self._states) - 1)
                self.tab_bar.setCurrentIndex(prev)
            self.new_tab_requested.emit()
        else:
            self._stack.setCurrentIndex(index)
            self.tab_changed.emit(index)

    def _on_close_requested(self, index: int):
        """Block closing the + tab; otherwise emit tab_close_requested."""
        if index == self._plus_index:
            return
        self.tab_close_requested.emit(index)
