# PDF Viewer Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the PDF viewer from a script-launched tool into a full desktop app with tabs, a collapsible library sidebar, compact header, and a Windows installer.

**Architecture:** Extract per-document state (PDFEngine, PageRenderer, EditTracker, SearchEngine, UndoStack) into a `TabState` dataclass managed by a `TabManager`. The main window becomes a shell that swaps active tab state when the user switches tabs. A `LibrarySidebar` widget on the right tracks all opened PDFs with thumbnails. The toolbar absorbs the menu bar behind a hamburger button. Config and library data are stored in `%APPDATA%\PDFViewer\`. PyInstaller bundles the app, Inno Setup creates the installer.

**Tech Stack:** Python 3.11+, PySide6 6.7+, PyMuPDF (fitz) 1.24+, PyInstaller, Inno Setup

**Spec:** `docs/superpowers/specs/2026-03-31-pdf-viewer-upgrade-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `config.py` | Modify | Add AppData path resolution, sidebar_collapsed and library_path keys |
| `tab_manager.py` | Create | TabState dataclass, TabManager (QTabBar wrapper), tab lifecycle |
| `library_sidebar.py` | Create | LibrarySidebar widget, LibraryCard widget, library.json I/O, thumbnail caching |
| `toolbar.py` | Modify | Add hamburger menu button, remove page navigator (moves to status bar) |
| `main.py` | Modify | Replace single-engine with TabManager, add sidebar, rewire signals, single-instance |
| `search.py` | No change | SearchEngine/SearchBar are already stateless per-use |
| `editor.py` | No change | EditTracker/commands are already independent instances |
| `page_renderer.py` | No change | Already takes engine + theme as constructor args |
| `render_worker.py` | No change | Already independent per-instance |
| `pdf_engine.py` | No change | Already independent per-instance |
| `text_overlay.py` | No change | Already independent per-instance |
| `theme_engine.py` | No change | Stays global (app-wide theme) |
| `icon.ico` | Create | App icon file |
| `build.bat` | Create | PyInstaller build script |
| `PDFViewer.spec` | Create | PyInstaller spec file |
| `installer.iss` | Create | Inno Setup installer script |

---

### Task 1: Move Config to AppData

**Files:**
- Modify: `config.py`
- Modify: `main.py:23-29` (CONFIG_PATH usage)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
import os
from unittest.mock import patch
from config import get_appdata_dir, get_config_path


def test_get_appdata_dir_returns_appdata_path():
    with patch.dict(os.environ, {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}):
        result = get_appdata_dir()
        assert result.name == "PDFViewer"
        assert "AppData" in str(result)


def test_get_config_path_inside_appdata():
    with patch.dict(os.environ, {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}):
        result = get_config_path()
        assert result.name == "config.json"
        assert "PDFViewer" in str(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_config.py::test_get_appdata_dir_returns_appdata_path tests/test_config.py::test_get_config_path_inside_appdata -v`
Expected: FAIL — `get_appdata_dir` and `get_config_path` not defined

- [ ] **Step 3: Implement AppData path resolution**

In `config.py`, add these functions before `load_config`:

```python
def get_appdata_dir() -> Path:
    """Return %APPDATA%/PDFViewer, creating it if needed."""
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = appdata / "PDFViewer"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    """Return path to config.json in AppData."""
    return get_appdata_dir() / "config.json"
```

Add `import os` at the top of `config.py`.

Add `sidebar_collapsed` and `library_path` fields to `AppConfig`:

```python
@dataclass
class AppConfig:
    theme: str = "dark"
    custom_bg_color: str = "#1E1E1E"
    custom_font_color: str = "#D4D4D4"
    display_mode: str = "reading"
    zoom_level: int = 100
    window_width: int = 1200
    window_height: int = 800
    window_x: int = 100
    window_y: int = 100
    last_opened_file: str = ""
    render_dpi: int = 150
    sidebar_collapsed: bool = False
```

- [ ] **Step 4: Update main.py to use AppData config path**

In `main.py`, replace:

```python
CONFIG_PATH = Path(__file__).parent / "config.json"
```

with:

```python
from config import AppConfig, load_config, save_config, get_config_path

CONFIG_PATH = get_config_path()
```

Remove the duplicate `from config import AppConfig, load_config, save_config` import that's already at the top (merge them).

- [ ] **Step 5: Migrate existing config.json if present**

In `main.py` `MainWindow.__init__`, before loading config, add migration logic:

```python
# Migrate config from old location if needed
old_config = Path(__file__).parent / "config.json"
if old_config.exists() and not CONFIG_PATH.exists():
    import shutil
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_config, CONFIG_PATH)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add config.py main.py tests/test_config.py
git commit -m "feat: move config storage to %APPDATA%/PDFViewer"
```

---

### Task 2: Create TabState and TabManager

**Files:**
- Create: `tab_manager.py`
- Test: `tests/test_tab_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tab_manager.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from tab_manager import TabState, TabManager


def test_tab_state_creation():
    """TabState holds per-tab components."""
    state = TabState.__new__(TabState)
    state.file_path = None
    state.engine = MagicMock()
    state.renderer = MagicMock()
    state.edit_tracker = MagicMock()
    state.search_engine = MagicMock()
    state.undo_stack = MagicMock()
    assert state.file_path is None
    assert state.engine is not None


@pytest.fixture
def mock_theme():
    theme = MagicMock()
    theme.bg_color = MagicMock()
    theme.font_color = MagicMock()
    return theme


def test_tab_manager_starts_empty(qtbot, mock_theme):
    """TabManager starts with no tabs."""
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    assert manager.count() == 0
    assert manager.active_tab() is None


def test_tab_manager_add_tab(qtbot, mock_theme):
    """Adding a tab creates a TabState and makes it active."""
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state = manager.add_tab("test.pdf")
    assert manager.count() == 1
    assert manager.active_tab() is state
    assert state.file_path is None  # Not opened yet, just created


def test_tab_manager_remove_tab(qtbot, mock_theme):
    """Removing a tab cleans up and adjusts active tab."""
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state1 = manager.add_tab("first.pdf")
    state2 = manager.add_tab("second.pdf")
    manager.remove_tab(0)
    assert manager.count() == 1
    assert manager.active_tab() is state2


def test_tab_manager_switch_tab(qtbot, mock_theme):
    """Switching tabs changes the active state."""
    manager = TabManager(theme_engine=mock_theme)
    qtbot.addWidget(manager)
    state1 = manager.add_tab("first.pdf")
    state2 = manager.add_tab("second.pdf")
    manager.tab_bar.setCurrentIndex(0)
    assert manager.active_tab() is state1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_tab_manager.py -v`
Expected: FAIL — `tab_manager` module not found

- [ ] **Step 3: Implement TabState and TabManager**

Create `tab_manager.py`:

```python
"""Tab management: per-tab state and tab bar controller."""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QWidget, QTabBar, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QUndoStack

from pdf_engine import PDFEngine
from page_renderer import PageRenderer
from render_worker import RenderWorker
from text_overlay import SelectionManager
from editor import EditTracker
from search import SearchEngine
from theme_engine import ThemeEngine


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

    def init_selection_manager(self):
        """Initialize selection manager after renderer scene is ready."""
        self.selection_manager = SelectionManager(
            self.renderer.scene, self.renderer.overlay_manager
        )

    def close(self):
        """Clean up resources for this tab."""
        self.renderer.close_document()
        self.engine.close()


class TabManager(QWidget):
    """Manages a QTabBar and a QStackedWidget of PageRenderer views."""

    tab_changed = Signal(int)        # index of new active tab
    tab_close_requested = Signal(int)  # index of tab to close
    new_tab_requested = Signal()     # + button clicked

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._theme = theme_engine
        self._tabs: list[TabState] = []

        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(False)
        self.tab_bar.setExpanding(False)

        # Add "+" button as a non-closable tab at the end
        self._plus_index = self.tab_bar.addTab("+")
        self.tab_bar.setTabButton(self._plus_index, QTabBar.ButtonPosition.RightSide, None)
        self.tab_bar.setTabButton(self._plus_index, QTabBar.ButtonPosition.LeftSide, None)

        self._stack = QStackedWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_bar)
        layout.addWidget(self._stack)

        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_close_requested)

    def count(self) -> int:
        """Number of document tabs (excludes the + button)."""
        return len(self._tabs)

    def active_tab(self) -> TabState | None:
        """Return the currently active TabState, or None."""
        idx = self.tab_bar.currentIndex()
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    def tab_at(self, index: int) -> TabState | None:
        """Return TabState at index, or None."""
        if 0 <= index < len(self._tabs):
            return self._tabs[index]
        return None

    def add_tab(self, label: str) -> TabState:
        """Create a new tab with fresh per-document state."""
        state = TabState(theme_engine=self._theme, parent_widget=self)
        state.init_selection_manager()
        self._tabs.append(state)

        # Insert before the "+" tab
        insert_at = self.tab_bar.count() - 1
        self.tab_bar.insertTab(insert_at, label)
        self._stack.addWidget(state.renderer.view)

        # Switch to the new tab
        self.tab_bar.setCurrentIndex(insert_at)
        return state

    def remove_tab(self, index: int):
        """Remove tab at index and clean up its state."""
        if index < 0 or index >= len(self._tabs):
            return

        state = self._tabs.pop(index)
        self.tab_bar.removeTab(index)
        self._stack.removeWidget(state.renderer.view)
        state.close()

    def update_tab_label(self, index: int, label: str):
        """Update the display label for a tab."""
        if 0 <= index < len(self._tabs):
            self.tab_bar.setTabText(index, label)

    def index_of_path(self, path: Path) -> int:
        """Return tab index for a file path, or -1 if not open."""
        for i, state in enumerate(self._tabs):
            if state.file_path and state.file_path.resolve() == path.resolve():
                return i
        return -1

    def _on_tab_changed(self, index: int):
        # If they clicked the "+" tab, switch back and emit new_tab_requested
        if index == self.tab_bar.count() - 1 and index >= len(self._tabs):
            if self._tabs:
                self.tab_bar.setCurrentIndex(len(self._tabs) - 1)
            self.new_tab_requested.emit()
            return

        if 0 <= index < len(self._tabs):
            self._stack.setCurrentWidget(self._tabs[index].renderer.view)
            self.tab_changed.emit(index)

    def _on_close_requested(self, index: int):
        # Don't allow closing the "+" button
        if index >= len(self._tabs):
            return
        self.tab_close_requested.emit(index)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_tab_manager.py -v`
Expected: PASS (note: requires `pytest-qt` — install if needed: `pip install pytest-qt`)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add tab_manager.py tests/test_tab_manager.py
git commit -m "feat: add TabState and TabManager for multi-tab support"
```

---

### Task 3: Create Library Sidebar

**Files:**
- Create: `library_sidebar.py`
- Test: `tests/test_library_sidebar.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_library_sidebar.py`:

```python
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
    assert len(data.entries) == 1  # No duplicate


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
    # Most recently added/updated should be first
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_library_sidebar.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement LibraryData and LibraryEntry**

Create `library_sidebar.py`:

```python
"""Collapsible library sidebar with PDF grid and thumbnail cards."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QFrame, QMenu, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter, QAction


@dataclass
class LibraryEntry:
    file_path: str
    filename: str
    page_count: int
    last_opened: str
    thumb_path: str = ""


class LibraryData:
    """Manages the library.json data file."""

    def __init__(self, path: Path):
        self._path = path
        self.entries: list[LibraryEntry] = []

    def load(self):
        """Load entries from disk."""
        if not self._path.exists():
            self.entries = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self.entries = [LibraryEntry(**e) for e in data]
        except (json.JSONDecodeError, TypeError, KeyError):
            self.entries = []

    def save(self):
        """Save entries to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self.entries]
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_or_update(self, file_path: str, filename: str, page_count: int):
        """Add or update an entry, moving it to the front (most recent)."""
        now = datetime.now(timezone.utc).isoformat()
        # Remove existing entry for this path
        self.entries = [e for e in self.entries if e.file_path != file_path]
        # Insert at front
        entry = LibraryEntry(
            file_path=file_path,
            filename=filename,
            page_count=page_count,
            last_opened=now,
        )
        self.entries.insert(0, entry)
        return entry

    def remove(self, file_path: str):
        """Remove an entry by file path."""
        self.entries = [e for e in self.entries if e.file_path != file_path]

    def find(self, file_path: str) -> LibraryEntry | None:
        """Find an entry by file path."""
        for e in self.entries:
            if e.file_path == file_path:
                return e
        return None


class LibraryCard(QFrame):
    """A card widget showing a PDF thumbnail, filename, and metadata."""

    clicked = Signal(str)          # file_path
    remove_requested = Signal(str)  # file_path

    def __init__(self, entry: LibraryEntry, parent=None):
        super().__init__(parent)
        self._entry = entry
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedHeight(80)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: white; border-radius: 3px;"
        )
        layout.addWidget(self._thumb_label)

        # Load thumbnail if available
        if entry.thumb_path and Path(entry.thumb_path).exists():
            pixmap = QPixmap(entry.thumb_path)
            self._thumb_label.setPixmap(
                pixmap.scaled(self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )

        # Filename
        name_label = QLabel(entry.filename)
        name_label.setWordWrap(False)
        name_label.setStyleSheet("font-size: 11px; font-weight: 500;")
        name_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(name_label)

        # Metadata
        meta_text = self._format_meta(entry)
        meta_label = QLabel(meta_text)
        meta_label.setStyleSheet("font-size: 9px; color: #888;")
        layout.addWidget(meta_label)

        # Check if file exists
        if not Path(entry.file_path).exists():
            self.setStyleSheet("opacity: 0.5;")
            name_label.setStyleSheet("font-size: 11px; font-weight: 500; color: #888;")

    def _format_meta(self, entry: LibraryEntry) -> str:
        pages = f"{entry.page_count} page{'s' if entry.page_count != 1 else ''}"
        try:
            opened = datetime.fromisoformat(entry.last_opened)
            now = datetime.now(timezone.utc)
            delta = now - opened
            if delta.total_seconds() < 60:
                time_str = "just now"
            elif delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() / 60)
                time_str = f"{mins}m ago"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() / 3600)
                time_str = f"{hours}h ago"
            elif delta.days == 1:
                time_str = "yesterday"
            else:
                time_str = f"{delta.days} days ago"
        except (ValueError, TypeError):
            time_str = ""
        return f"{pages} · {time_str}" if time_str else pages

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry.file_path)
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self.clicked.emit(self._entry.file_path))
        menu.addAction(open_action)

        remove_action = QAction("Remove from Library", self)
        remove_action.triggered.connect(lambda: self.remove_requested.emit(self._entry.file_path))
        menu.addAction(remove_action)

        menu.exec(self.mapToGlobal(pos))

    def update_thumbnail(self, thumb_path: str):
        """Update the thumbnail image from a cached file."""
        if Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            self._thumb_label.setPixmap(
                pixmap.scaled(self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )


class LibrarySidebar(QWidget):
    """Collapsible sidebar showing the PDF library grid."""

    pdf_open_requested = Signal(str)  # file_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._cards: list[LibraryCard] = []

        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Toggle strip
        self._toggle_btn = QPushButton("›")
        self._toggle_btn.setFixedWidth(20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { border: none; background: #181825; color: #6c7086; font-size: 14px; }"
            "QPushButton:hover { background: #313244; }"
        )
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        self._main_layout.addWidget(self._toggle_btn)

        # Content panel
        self._content = QWidget()
        self._content.setFixedWidth(200)
        self._content.setStyleSheet("background-color: #181825;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(4)

        # Header
        header = QLabel("Library")
        header.setStyleSheet("font-size: 12px; font-weight: 600; color: #a6adc8; padding: 4px;")
        content_layout.addWidget(header)

        # Scroll area for cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(6)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        content_layout.addWidget(self._scroll)

        self._main_layout.addWidget(self._content)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        """Set collapsed state."""
        self._collapsed = collapsed
        self._content.setVisible(not collapsed)
        self._toggle_btn.setText("‹" if collapsed else "›")

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def refresh(self, entries: list[LibraryEntry]):
        """Rebuild card widgets from the current library entries."""
        # Clear existing cards
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        # Remove the stretch
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add cards
        for entry in entries:
            card = LibraryCard(entry)
            card.clicked.connect(self.pdf_open_requested.emit)
            card.remove_requested.connect(self._on_remove_requested)
            self._card_layout.addWidget(card)
            self._cards.append(card)

        self._card_layout.addStretch()

    def _on_remove_requested(self, file_path: str):
        """Emit removal signal — main window handles data update."""
        # This is handled by the main window connecting to the library data
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_library_sidebar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add library_sidebar.py tests/test_library_sidebar.py
git commit -m "feat: add library sidebar with data persistence and card widgets"
```

---

### Task 4: Refactor Toolbar — Hamburger Menu + Compact Layout

**Files:**
- Modify: `toolbar.py`
- Test: `tests/test_toolbar.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_toolbar.py`:

```python
from toolbar import ToolBar


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
    """Page navigator should be removed from toolbar (moved to status bar)."""
    toolbar = ToolBar()
    qtbot.addWidget(toolbar)
    assert not hasattr(toolbar, 'page_spinbox')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_toolbar.py::test_toolbar_has_hamburger tests/test_toolbar.py::test_toolbar_hamburger_menu_has_actions tests/test_toolbar.py::test_toolbar_no_page_navigator -v`
Expected: FAIL

- [ ] **Step 3: Refactor toolbar.py**

Replace the contents of `toolbar.py`:

```python
"""Unified toolbar with hamburger menu, file actions, theme, and zoom controls."""

from PySide6.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QLabel, QColorDialog, QMenu, QToolButton,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal


class ToolBar(QToolBar):
    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    theme_selected = Signal(str)
    bg_color_selected = Signal(str)
    font_color_selected = Signal(str)
    zoom_selected = Signal(str)
    mode_toggle_requested = Signal()
    find_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self._build_hamburger()
        self.addSeparator()
        self._build_file_actions()
        self.addSeparator()
        self._build_theme_controls()
        self.addSeparator()
        self._build_zoom_controls()

    def _build_hamburger(self):
        self.hamburger_btn = QToolButton()
        self.hamburger_btn.setText("☰")
        self.hamburger_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.hamburger_btn.setStyleSheet("font-size: 16px; padding: 2px 6px;")

        menu = QMenu(self.hamburger_btn)

        # File section
        menu.addAction(self._make_action("Open", "Ctrl+O", self.open_requested.emit, menu))
        self.save_menu_action = self._make_action("Save", "Ctrl+S", self.save_requested.emit, menu)
        self.save_menu_action.setEnabled(False)
        menu.addAction(self.save_menu_action)
        menu.addAction(self._make_action("Save As", "Ctrl+Shift+S", self.save_as_requested.emit, menu))
        menu.addSeparator()

        # Edit section
        self.undo_action = QAction("Undo", menu)
        self.undo_action.setShortcut("Ctrl+Z")
        menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", menu)
        self.redo_action.setShortcut("Ctrl+Y")
        menu.addAction(self.redo_action)
        menu.addSeparator()

        # View section
        menu.addAction(self._make_action("Find", "Ctrl+F", self.find_requested.emit, menu))
        self.mode_action = self._make_action(
            "Toggle Reading/Faithful Mode", "F5", self.mode_toggle_requested.emit, menu
        )
        menu.addAction(self.mode_action)

        self.hamburger_btn.setMenu(menu)
        self.addWidget(self.hamburger_btn)

    def _make_action(self, text: str, shortcut: str, slot, parent) -> QAction:
        action = QAction(text, parent)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    def _build_file_actions(self):
        self.open_action = QAction("Open", self)
        self.open_action.triggered.connect(self.open_requested.emit)
        self.addAction(self.open_action)
        self.save_action = QAction("Save", self)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_requested.emit)
        self.addAction(self.save_action)
        self.save_as_action = QAction("Save As", self)
        self.save_as_action.triggered.connect(self.save_as_requested.emit)
        self.addAction(self.save_as_action)

    def _build_theme_controls(self):
        self.addWidget(QLabel(" Theme: "))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Sepia", "Dark", "AMOLED Dark", "Custom"])
        self.theme_combo.setCurrentText("Dark")
        self.theme_combo.currentTextChanged.connect(
            lambda t: self.theme_selected.emit(t.lower().replace(" ", "_")))
        self.addWidget(self.theme_combo)
        self.bg_color_btn = QPushButton("BG")
        self.bg_color_btn.setToolTip("Background Color")
        self.bg_color_btn.setFixedWidth(40)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        self.addWidget(self.bg_color_btn)
        self.font_color_btn = QPushButton("Font")
        self.font_color_btn.setToolTip("Font Color")
        self.font_color_btn.setFixedWidth(45)
        self.font_color_btn.clicked.connect(self._pick_font_color)
        self.addWidget(self.font_color_btn)

    def _build_zoom_controls(self):
        self.addWidget(QLabel(" Zoom: "))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "300%", "Fit Width", "Fit Page"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(
            lambda t: self.zoom_selected.emit(t.replace("%", "").strip().lower().replace(" ", "_")))
        self.addWidget(self.zoom_combo)

    def set_dirty(self, dirty: bool):
        self.save_action.setEnabled(dirty)
        self.save_menu_action.setEnabled(dirty)

    def connect_undo_stack(self, undo_stack):
        """Connect undo/redo actions to an undo stack."""
        self.undo_action.triggered.disconnect() if self.undo_action.receivers(self.undo_action.triggered) else None
        self.redo_action.triggered.disconnect() if self.redo_action.receivers(self.redo_action.triggered) else None
        self.undo_action.triggered.connect(undo_stack.undo)
        self.redo_action.triggered.connect(undo_stack.redo)

    def _pick_bg_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color_selected.emit(color.name())

    def _pick_font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.font_color_selected.emit(color.name())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/test_toolbar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add toolbar.py tests/test_toolbar.py
git commit -m "feat: refactor toolbar with hamburger menu, remove page navigator"
```

---

### Task 5: Rewrite MainWindow for Tabs + Sidebar Integration

**Files:**
- Modify: `main.py`

This is the largest task — it rewires MainWindow to use TabManager and LibrarySidebar. Since the core logic (editing, saving, searching) is mostly the same but now operates on `active_tab()` instead of direct instance variables, this is primarily a refactor.

- [ ] **Step 1: Rewrite MainWindow imports and __init__**

Replace the imports and `__init__` in `main.py`:

```python
"""Entry point: QApplication, MainWindow, tabs, sidebar, shortcuts, integration."""

import sys
import os
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QStatusBar, QGraphicsTextItem, QGraphicsRectItem,
    QLabel, QSpinBox, QSplitter,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF, QPointF
from PySide6.QtGui import QAction, QColor, QKeySequence, QPen, QBrush, QShortcut

from config import AppConfig, load_config, save_config, get_config_path, get_appdata_dir
from pdf_engine import PDFEngine
from page_renderer import PageRenderer
from text_overlay import SpanOverlay, SelectionManager
from theme_engine import ThemeEngine
from editor import EditTracker, BlockEditCommand
from search import SearchEngine, SearchBar
from toolbar import ToolBar
from tab_manager import TabManager, TabState
from library_sidebar import LibrarySidebar, LibraryData

CONFIG_PATH = get_config_path()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._config = load_config(CONFIG_PATH)
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_config)

        # Migrate old config if needed
        old_config = Path(__file__).parent / "config.json"
        if old_config.exists() and not CONFIG_PATH.exists():
            import shutil
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_config, CONFIG_PATH)

        # Global theme (app-wide)
        self._theme_engine = ThemeEngine()
        self._theme_engine.set_theme(self._config.theme)
        self._theme_engine.set_display_mode(self._config.display_mode)

        # Library data
        self._library_data = LibraryData(get_appdata_dir() / "library.json")
        self._library_data.load()
        self._thumbs_dir = get_appdata_dir() / ".thumbs"
        self._thumbs_dir.mkdir(parents=True, exist_ok=True)

        # UI setup
        self.setWindowTitle("PDF Viewer")
        self._setup_ui()
        self._setup_shortcuts()
        self._setup_connections()

        # Restore window geometry
        self.resize(self._config.window_width, self._config.window_height)
        self.move(self._config.window_x, self._config.window_y)

        # Restore sidebar state
        self._sidebar.set_collapsed(self._config.sidebar_collapsed)

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Refresh library sidebar
        self._sidebar.refresh(self._library_data.entries)
```

- [ ] **Step 2: Rewrite _setup_ui**

Replace `_setup_ui` in `main.py`:

```python
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar (row 2 — below tabs)
        self._toolbar = ToolBar(self)
        self.addToolBar(self._toolbar)

        # Tab manager (row 1 — tabs at top) + content area
        self._tab_manager = TabManager(theme_engine=self._theme_engine)

        # Search bar
        self._search_bar = SearchBar()

        # Content area: tab views + sidebar
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left side: tabs + search bar
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._tab_manager.tab_bar)
        left_layout.addWidget(self._search_bar)
        left_layout.addWidget(self._tab_manager._stack)

        # Empty state label (shown when no tabs open)
        self._empty_label = QLabel("Open a PDF or drag one here")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("font-size: 16px; color: #6c7086; padding: 40px;")
        left_layout.addWidget(self._empty_label)

        content_layout.addWidget(left_panel, 1)

        # Right side: library sidebar
        self._sidebar = LibrarySidebar()
        content_layout.addWidget(self._sidebar)

        main_layout.addLayout(content_layout)

        # Status bar with page navigator
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # Page navigator in status bar
        self._page_spinbox = QSpinBox()
        self._page_spinbox.setMinimum(1)
        self._page_spinbox.setMaximum(1)
        self._page_spinbox.valueChanged.connect(self._on_page_jump)
        self._page_total_label = QLabel("/ 0")
        self._status_bar.addPermanentWidget(QLabel("Page: "))
        self._status_bar.addPermanentWidget(self._page_spinbox)
        self._status_bar.addPermanentWidget(self._page_total_label)

        self._status_bar.showMessage("Ready")
        self._update_empty_state()
```

- [ ] **Step 3: Rewrite _setup_shortcuts**

Replace `_setup_shortcuts`:

```python
    def _setup_shortcuts(self):
        # Copy
        copy_action = QAction("Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self._copy_selection)
        self.addAction(copy_action)

        # Tab shortcuts
        QShortcut(QKeySequence("Ctrl+T"), self, self._open_dialog)
        QShortcut(QKeySequence("Ctrl+W"), self, self._close_current_tab)
        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)
        QShortcut(QKeySequence("Ctrl+\\"), self, self._sidebar.toggle_collapsed)

        # Ctrl+1-9 for tab jumping
        for i in range(1, 10):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            shortcut.activated.connect(lambda idx=i-1: self._jump_to_tab(idx))

        # Keyboard navigation
        for key, slot in [
            (Qt.Key.Key_Home, lambda: self._active_renderer_call("scroll_to_page", 0)),
            (Qt.Key.Key_End, lambda: self._active_renderer_call(
                "scroll_to_page", self._active_page_count() - 1)),
        ]:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _active_renderer_call(self, method: str, *args):
        """Call a method on the active tab's renderer if a tab is open."""
        tab = self._tab_manager.active_tab()
        if tab:
            getattr(tab.renderer, method)(*args)

    def _active_page_count(self) -> int:
        tab = self._tab_manager.active_tab()
        return tab.renderer.page_count if tab else 0
```

- [ ] **Step 4: Rewrite _setup_connections**

Replace `_setup_connections`:

```python
    def _setup_connections(self):
        # Toolbar signals
        self._toolbar.open_requested.connect(self._open_dialog)
        self._toolbar.save_requested.connect(self._save)
        self._toolbar.save_as_requested.connect(self._save_as)
        self._toolbar.theme_selected.connect(self._on_theme_selected)
        self._toolbar.bg_color_selected.connect(self._on_bg_color)
        self._toolbar.font_color_selected.connect(self._on_font_color)
        self._toolbar.zoom_selected.connect(self._on_zoom)
        self._toolbar.mode_toggle_requested.connect(self._theme_engine.toggle_display_mode)
        self._toolbar.find_requested.connect(self._show_search)

        # Tab manager signals
        self._tab_manager.tab_changed.connect(self._on_tab_changed)
        self._tab_manager.tab_close_requested.connect(self._close_tab)
        self._tab_manager.new_tab_requested.connect(self._open_dialog)

        # Search
        self._search_bar.search_requested.connect(self._on_search)
        self._search_bar.next_requested.connect(self._on_search_next)
        self._search_bar.prev_requested.connect(self._on_search_prev)
        self._search_bar.closed.connect(self._clear_search_highlights)

        # Library sidebar
        self._sidebar.pdf_open_requested.connect(lambda p: self.open_file(Path(p)))

        # Page jump
        self._page_spinbox.valueChanged.connect(self._on_page_jump)
```

- [ ] **Step 5: Rewrite open_file for tabs**

Replace `open_file`:

```python
    def open_file(self, path: Path):
        path = Path(path)
        if not path.exists():
            QMessageBox.warning(self, "Error", f"File not found: {path}")
            return

        # If already open in a tab, switch to it
        existing_idx = self._tab_manager.index_of_path(path)
        if existing_idx >= 0:
            self._tab_manager.tab_bar.setCurrentIndex(existing_idx)
            return

        # Create new tab
        tab = self._tab_manager.add_tab(path.name)
        self._update_empty_state()

        # Try opening with password retry
        try:
            needs_pass = tab.renderer.open_document(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open file: {e}")
            idx = self._tab_manager.tab_bar.currentIndex()
            self._tab_manager.remove_tab(idx)
            self._update_empty_state()
            return

        if needs_pass:
            for attempt in range(3):
                password, ok = QInputDialog.getText(
                    self, "Password Required",
                    f"Enter PDF password (attempt {attempt + 1}/3):",
                    QInputDialog.InputMode.TextInput,
                )
                if not ok:
                    idx = self._tab_manager.tab_bar.currentIndex()
                    self._tab_manager.remove_tab(idx)
                    self._update_empty_state()
                    return
                needs_pass = tab.renderer.open_document(path, password)
                if not needs_pass:
                    break
            else:
                QMessageBox.warning(self, "Error", "Failed to authenticate after 3 attempts.")
                idx = self._tab_manager.tab_bar.currentIndex()
                self._tab_manager.remove_tab(idx)
                self._update_empty_state()
                return

        tab.file_path = path
        self._update_title()
        self._update_page_info(tab)
        self._toolbar.set_dirty(False)
        self._status_bar.showMessage(f"Opened: {path.name}")

        # Connect render worker signals for search
        tab.renderer._render_worker.search_text_ready.connect(
            lambda pn, txt, se=tab.search_engine: se.set_page_text(pn, txt)
        )
        tab.renderer._render_worker.search_index_complete.connect(
            lambda se=tab.search_engine: se.mark_ready()
        )

        # Install event filter for edit mode
        tab.renderer.view.viewport().installEventFilter(self)

        # Connect page changed signal
        tab.renderer.page_changed.connect(lambda p: self._on_page_changed(p))

        # Check for scanned PDF
        if tab.renderer.page_count > 0:
            spans = tab.engine.extract_spans(0)
            if not spans:
                self._status_bar.showMessage("This PDF is image-based. Text editing is not available.")

        # Connect undo stack to toolbar
        self._toolbar.connect_undo_stack(tab.undo_stack)

        # Add to library
        self._add_to_library(path, tab.renderer.page_count)

        self._config.last_opened_file = str(path)
        self._schedule_config_save()

    def _add_to_library(self, path: Path, page_count: int):
        """Add/update a PDF in the library and generate thumbnail."""
        self._library_data.add_or_update(str(path), path.name, page_count)

        # Generate thumbnail
        try:
            import fitz
            doc = fitz.open(str(path))
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(0.3, 0.3))
                thumb_path = self._thumbs_dir / f"{path.stem}_{hash(str(path)) & 0xFFFFFFFF}.png"
                pix.save(str(thumb_path))
                entry = self._library_data.find(str(path))
                if entry:
                    entry.thumb_path = str(thumb_path)
            doc.close()
        except Exception:
            pass

        self._library_data.save()
        self._sidebar.refresh(self._library_data.entries)
```

- [ ] **Step 6: Add tab navigation and lifecycle methods**

Add these methods to `MainWindow`:

```python
    def _on_tab_changed(self, index: int):
        """Handle tab switch — rewire toolbar, search, page info."""
        tab = self._tab_manager.active_tab()
        if tab is None:
            return
        self._update_title()
        self._update_page_info(tab)
        self._toolbar.set_dirty(tab.edit_tracker.is_dirty)
        self._toolbar.connect_undo_stack(tab.undo_stack)
        self._clear_search_highlights()

    def _close_tab(self, index: int):
        """Handle tab close request — check for unsaved edits."""
        tab = self._tab_manager.tab_at(index)
        if tab is None:
            return
        if tab.edit_tracker.is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes", f"Save changes to {tab.file_path.name if tab.file_path else 'untitled'}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save_tab(tab)

        self._tab_manager.remove_tab(index)
        self._update_empty_state()
        self._update_title()

    def _close_current_tab(self):
        idx = self._tab_manager.tab_bar.currentIndex()
        if idx >= 0 and idx < self._tab_manager.count():
            self._close_tab(idx)

    def _next_tab(self):
        if self._tab_manager.count() <= 1:
            return
        idx = (self._tab_manager.tab_bar.currentIndex() + 1) % self._tab_manager.count()
        self._tab_manager.tab_bar.setCurrentIndex(idx)

    def _prev_tab(self):
        if self._tab_manager.count() <= 1:
            return
        idx = (self._tab_manager.tab_bar.currentIndex() - 1) % self._tab_manager.count()
        self._tab_manager.tab_bar.setCurrentIndex(idx)

    def _jump_to_tab(self, index: int):
        if 0 <= index < self._tab_manager.count():
            self._tab_manager.tab_bar.setCurrentIndex(index)

    def _update_empty_state(self):
        """Show/hide empty state label based on tab count."""
        has_tabs = self._tab_manager.count() > 0
        self._empty_label.setVisible(not has_tabs)
        self._tab_manager._stack.setVisible(has_tabs)

    def _update_page_info(self, tab: TabState):
        """Update page spinbox and label for the given tab."""
        count = tab.renderer.page_count
        self._page_spinbox.blockSignals(True)
        self._page_spinbox.setMaximum(max(count, 1))
        self._page_spinbox.setValue(1)
        self._page_spinbox.blockSignals(False)
        self._page_total_label.setText(f"/ {count}")

    def _on_page_jump(self, page: int):
        tab = self._tab_manager.active_tab()
        if tab:
            tab.renderer.scroll_to_page(page - 1)

    def _on_page_changed(self, page_num: int):
        self._page_spinbox.blockSignals(True)
        self._page_spinbox.setValue(page_num + 1)
        self._page_spinbox.blockSignals(False)
```

- [ ] **Step 7: Update save methods to work with active tab**

Replace `_save`, `_save_as`, and `_save_to`:

```python
    def _save(self):
        tab = self._tab_manager.active_tab()
        if not tab or not tab.file_path or not tab.edit_tracker.is_dirty:
            return
        self._save_tab(tab)

    def _save_as(self):
        tab = self._tab_manager.active_tab()
        if not tab:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF As", str(Path.home()), "PDF Files (*.pdf)")
        if path:
            self._save_tab(tab, Path(path))

    def _save_tab(self, tab: TabState, save_path: Path | None = None):
        """Save a specific tab's document."""
        path = save_path or tab.file_path
        if not path:
            return
        try:
            edits = tab.edit_tracker.dirty_edits
            block_edits = tab.edit_tracker.dirty_block_edits
            if not edits and not block_edits:
                return

            temp_dir = path.parent
            try:
                tmp = tempfile.NamedTemporaryFile(dir=str(temp_dir), suffix=".pdf", delete=False)
                tmp_path = Path(tmp.name)
                tmp.close()
            except OSError:
                alt_path, _ = QFileDialog.getSaveFileName(
                    self, "Save PDF As (original location not writable)",
                    str(Path.home() / "Documents"), "PDF Files (*.pdf)",
                )
                if not alt_path:
                    return
                tmp = tempfile.NamedTemporaryFile(dir=str(Path(alt_path).parent), suffix=".pdf", delete=False)
                tmp_path = Path(tmp.name)
                tmp.close()
                path = Path(alt_path)

            warnings = tab.engine.save_edits(edits, tmp_path, block_edits=block_edits)

            tab.engine.close()
            tab.renderer.close_document()

            bak_path = path.with_suffix(".pdf.bak")
            if path.exists():
                if bak_path.exists():
                    bak_path.unlink()
                path.rename(bak_path)
            tmp_path.rename(path)

            tab.renderer.open_document(path)
            tab.file_path = path

            if bak_path.exists():
                bak_path.unlink()

            tab.edit_tracker.clear()
            tab.undo_stack.clear()
            self._toolbar.set_dirty(False)
            self._update_title()

            for w in warnings:
                self._status_bar.showMessage(w, 5000)
            self._status_bar.showMessage(f"Saved: {path.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
```

- [ ] **Step 8: Update title, theme, zoom, and search methods**

Replace these methods:

```python
    def _on_dirty_changed(self, dirty: bool):
        self._toolbar.set_dirty(dirty)
        self._update_title(dirty)

    def _update_title(self, dirty: bool | None = None):
        tab = self._tab_manager.active_tab()
        name = tab.file_path.name if tab and tab.file_path else ""
        is_dirty = dirty if dirty is not None else (tab.edit_tracker.is_dirty if tab else False)
        prefix = "* " if is_dirty else ""
        self.setWindowTitle(f"{prefix}{name} — PDF Viewer" if name else "PDF Viewer")
        # Update tab label too
        if tab and tab.file_path:
            idx = self._tab_manager.tab_bar.currentIndex()
            label = f"{'* ' if is_dirty else ''}{tab.file_path.name}"
            self._tab_manager.update_tab_label(idx, label)

    # --- Theme ---
    def _on_theme_selected(self, theme_name: str):
        self._theme_engine.set_theme(theme_name)
        self._config.theme = theme_name
        self._schedule_config_save()

    def _on_bg_color(self, color: str):
        self._theme_engine.set_custom_colors(color, self._theme_engine.font_color.name())
        self._config.custom_bg_color = color
        self._toolbar.theme_combo.setCurrentText("Custom")
        self._schedule_config_save()

    def _on_font_color(self, color: str):
        self._theme_engine.set_custom_colors(self._theme_engine.bg_color.name(), color)
        self._config.custom_font_color = color
        self._toolbar.theme_combo.setCurrentText("Custom")
        self._schedule_config_save()

    # --- Zoom ---
    def _on_zoom(self, value: str):
        tab = self._tab_manager.active_tab()
        if not tab:
            return
        if value == "fit_width":
            tab.renderer.fit_width()
        elif value == "fit_page":
            tab.renderer.fit_page()
        else:
            try:
                tab.renderer.set_zoom(int(value))
            except ValueError:
                pass

    # --- Search ---
    def _show_search(self):
        tab = self._tab_manager.active_tab()
        if tab and not tab.search_engine.is_ready:
            self._search_bar.set_indexing()
        self._search_bar.show_bar()

    def _on_search(self, query: str, case_sensitive: bool):
        tab = self._tab_manager.active_tab()
        if not tab:
            return
        self._clear_search_highlights()
        if not tab.search_engine.is_ready or not query:
            self._search_bar.update_count(0, 0)
            return

        if tab.engine.is_open and tab.engine._doc is not None:
            results = tab.search_engine.search_with_quads(
                query, tab.engine._doc, case_sensitive
            )
        else:
            results = tab.search_engine.search(query, case_sensitive)
        tab.search_results = results
        tab.search_index = 0 if results else -1
        self._search_bar.update_count(tab.search_index, len(results))
        if results:
            self._jump_to_search_result(tab, 0)

    def _on_search_next(self):
        tab = self._tab_manager.active_tab()
        if not tab or not tab.search_results:
            return
        tab.search_index = (tab.search_index + 1) % len(tab.search_results)
        self._search_bar.update_count(tab.search_index, len(tab.search_results))
        self._jump_to_search_result(tab, tab.search_index)

    def _on_search_prev(self):
        tab = self._tab_manager.active_tab()
        if not tab or not tab.search_results:
            return
        tab.search_index = (tab.search_index - 1) % len(tab.search_results)
        self._search_bar.update_count(tab.search_index, len(tab.search_results))
        self._jump_to_search_result(tab, tab.search_index)

    def _jump_to_search_result(self, tab: TabState, index: int):
        self._clear_search_highlights()
        result = tab.search_results[index]
        page_num = result["page"]
        tab.renderer.scroll_to_page(page_num)

        if "rect" in result:
            scale = tab.renderer._scale
            y_offset = tab.renderer._page_y_offsets[page_num] if page_num < len(tab.renderer._page_y_offsets) else 0

            for i, r in enumerate(tab.search_results):
                if r["page"] != page_num or "rect" not in r:
                    continue
                rect = r["rect"]
                scene_rect = QRectF(
                    rect.x0 * scale, rect.y0 * scale + y_offset,
                    (rect.x1 - rect.x0) * scale, (rect.y1 - rect.y0) * scale,
                )
                highlight = QGraphicsRectItem(scene_rect)
                highlight.setPen(QPen(Qt.PenStyle.NoPen))
                if i == index:
                    highlight.setBrush(QBrush(self._search_color_active()))
                    tab.current_highlight = highlight
                else:
                    highlight.setBrush(QBrush(self._search_color_other()))
                highlight.setZValue(2.5)
                tab.renderer.scene.addItem(highlight)
                tab.search_highlights.append(highlight)

    def _clear_search_highlights(self):
        tab = self._tab_manager.active_tab()
        if not tab:
            return
        for h in tab.search_highlights:
            tab.renderer.scene.removeItem(h)
        tab.search_highlights.clear()
        tab.current_highlight = None

    def _search_color_active(self) -> QColor:
        if self._theme_engine.bg_color.lightnessF() < 0.5:
            return QColor(255, 165, 0, 140)
        return QColor(255, 165, 0, 100)

    def _search_color_other(self) -> QColor:
        if self._theme_engine.bg_color.lightnessF() < 0.5:
            return QColor(255, 255, 0, 110)
        return QColor(255, 255, 0, 80)
```

- [ ] **Step 9: Update eventFilter and edit methods to use active tab**

Replace `eventFilter`, `_handle_double_click`, `_enter_block_edit_mode`, `_exit_edit_mode`, `_discard_edit`, `_advance_to_next_block`, `_update_block_text`, and `_copy_selection`:

```python
    # --- Edit mode ---
    def eventFilter(self, obj, event):
        tab = self._tab_manager.active_tab()
        if tab and obj == tab.renderer.view.viewport():
            if event.type() == QEvent.Type.MouseButtonDblClick:
                scene_pos = tab.renderer.view.mapToScene(event.position().toPoint())
                self._handle_double_click(tab, scene_pos)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    tab._rubber_band_start = tab.renderer.view.mapToScene(event.position().toPoint())
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton and getattr(tab, '_rubber_band_start', None) is not None:
                    end = tab.renderer.view.mapToScene(event.position().toPoint())
                    rect = QRectF(tab._rubber_band_start, end).normalized()
                    if rect.width() > 5 and rect.height() > 5:
                        page_num = tab.renderer.current_page()
                        tab.selection_manager.select_rect(rect, page_num)
                    else:
                        tab.selection_manager.clear_selection()
                    tab._rubber_band_start = None
        return super().eventFilter(obj, event)

    def _handle_double_click(self, tab: TabState, scene_pos):
        page_num = tab.renderer.current_page()
        overlay = tab.renderer.overlay_manager.find_overlay_at(page_num, scene_pos)
        if overlay is not None:
            block_num = overlay.span_data["block_num"]
            self._enter_block_edit_mode(tab, block_num, page_num, scene_pos)

    def _enter_block_edit_mode(self, tab: TabState, block_num: int, page_num: int, click_scene_pos):
        if tab.active_edit is not None:
            self._exit_edit_mode(tab)

        blocks = tab.engine.extract_blocks(page_num)
        block_data = None
        for b in blocks:
            if b["block_num"] == block_num:
                block_data = b
                break
        if block_data is None or not block_data["text"].strip():
            return

        max_rect = tab.engine.compute_max_block_rect(page_num, block_num)

        block_overlays = tab.renderer.overlay_manager.get_block_overlays(page_num, block_num)
        for ov in block_overlays:
            ov._is_editing = True
            ov.hide()

        scale = tab.renderer._scale
        y_offset = tab.renderer._page_y_offsets[page_num] if page_num < len(tab.renderer._page_y_offsets) else 0
        bbox = block_data["bbox"]

        boundary = None
        if max_rect:
            boundary_rect = QRectF(
                max_rect[0] * scale, max_rect[1] * scale + y_offset,
                (max_rect[2] - max_rect[0]) * scale, (max_rect[3] - max_rect[1]) * scale,
            )
            boundary = QGraphicsRectItem(boundary_rect)
            pen = QPen(QColor(
                self._theme_engine.font_color.red(),
                self._theme_engine.font_color.green(),
                self._theme_engine.font_color.blue(),
                100,
            ))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.0)
            boundary.setPen(pen)
            boundary.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            boundary.setZValue(2.5)
            tab.renderer.scene.addItem(boundary)

        edit_item = QGraphicsTextItem(block_data["text"])
        font = edit_item.font()
        font.setPointSizeF(block_data["dominant_size"] * scale * 0.75)
        dom_flags = block_data["dominant_flags"]
        if dom_flags & (1 << 4):
            font.setBold(True)
        if dom_flags & (1 << 1):
            font.setItalic(True)
        if dom_flags & (1 << 3):
            font.setFamily("Courier")
        edit_item.setFont(font)
        edit_item.setPos(bbox[0] * scale, bbox[1] * scale + y_offset)
        block_width = (bbox[2] - bbox[0]) * scale
        edit_item.setTextWidth(block_width * 1.15)
        edit_item.setZValue(3)
        edit_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        edit_item.setDefaultTextColor(
            self._theme_engine.font_color if self._theme_engine.show_text_overlays else QColor(0, 0, 0)
        )

        tab.renderer.scene.addItem(edit_item)
        edit_item.setFocus()

        actual_rect = edit_item.mapRectToScene(edit_item.boundingRect())
        cover_rect = actual_rect.united(QRectF(
            bbox[0] * scale, bbox[1] * scale + y_offset,
            (bbox[2] - bbox[0]) * scale, (bbox[3] - bbox[1]) * scale,
        ))
        bg_cover = QGraphicsRectItem(cover_rect)
        bg_cover.setPen(QPen(Qt.PenStyle.NoPen))
        bg_cover.setBrush(QBrush(self._theme_engine.bg_color))
        bg_cover.setZValue(2.8)
        tab.renderer.scene.addItem(bg_cover)

        local_pos = edit_item.mapFromScene(click_scene_pos)
        cursor_pos = edit_item.document().documentLayout().hitTest(local_pos, Qt.HitTestAccuracy.FuzzyHit)
        if cursor_pos >= 0:
            cursor = edit_item.textCursor()
            cursor.setPosition(cursor_pos)
            edit_item.setTextCursor(cursor)

        tab.active_edit = {
            "type": "block",
            "block_num": block_num,
            "page_num": page_num,
            "block_data": block_data,
            "max_rect": max_rect,
            "edit_item": edit_item,
            "boundary": boundary,
            "bg_cover": bg_cover,
            "overlays": block_overlays,
            "original_text": block_data["text"],
        }

        original_key_press = edit_item.keyPressEvent

        def custom_key_press(event):
            if event.key() == Qt.Key.Key_Escape:
                self._discard_edit(tab)
            elif event.key() == Qt.Key.Key_Tab:
                self._exit_edit_mode(tab)
                self._advance_to_next_block(tab, page_num, block_num)
            else:
                original_key_press(event)

        edit_item.keyPressEvent = custom_key_press
        edit_item.focusOutEvent = lambda e: self._exit_edit_mode(tab)
        self._status_bar.showMessage("Editing paragraph — Escape to discard, click away to save")

    def _exit_edit_mode(self, tab: TabState | None = None):
        if tab is None:
            tab = self._tab_manager.active_tab()
        if tab is None or tab.active_edit is None:
            return

        edit_data = tab.active_edit
        tab.active_edit = None

        edit_item = edit_data["edit_item"]
        new_text = edit_item.toPlainText()
        original_text = edit_data["original_text"]

        tab.renderer.scene.removeItem(edit_item)
        if edit_data.get("boundary"):
            tab.renderer.scene.removeItem(edit_data["boundary"])
        if edit_data.get("bg_cover"):
            tab.renderer.scene.removeItem(edit_data["bg_cover"])

        for ov in edit_data["overlays"]:
            ov._is_editing = False
            ov.show()

        if new_text != original_text:
            block_data = edit_data["block_data"]
            cmd = BlockEditCommand(
                tracker=tab.edit_tracker,
                page_num=edit_data["page_num"],
                block_num=edit_data["block_num"],
                old_text=original_text,
                new_text=new_text,
                block_bbox=block_data["bbox"],
                extended_bbox=edit_data["max_rect"],
                font=block_data["dominant_font"],
                size=block_data["dominant_size"],
                color=block_data["dominant_color"],
                flags=block_data["dominant_flags"],
                align=block_data["align"],
                text_updater=lambda pn, bn, txt: self._update_block_text(tab, pn, bn, txt),
            )
            tab.undo_stack.push(cmd)
            self._on_dirty_changed(tab.edit_tracker.is_dirty)

        self._status_bar.showMessage("Ready")

    def _discard_edit(self, tab: TabState | None = None):
        if tab is None:
            tab = self._tab_manager.active_tab()
        if tab is None or tab.active_edit is None:
            return

        edit_data = tab.active_edit
        tab.active_edit = None

        tab.renderer.scene.removeItem(edit_data["edit_item"])
        if edit_data.get("boundary"):
            tab.renderer.scene.removeItem(edit_data["boundary"])
        if edit_data.get("bg_cover"):
            tab.renderer.scene.removeItem(edit_data["bg_cover"])

        for ov in edit_data["overlays"]:
            ov._is_editing = False
            ov.show()

        self._status_bar.showMessage("Edit discarded")

    def _advance_to_next_block(self, tab: TabState, page_num: int, current_block_num: int):
        blocks = tab.engine.extract_blocks(page_num)
        sorted_blocks = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        for i, b in enumerate(sorted_blocks):
            if b["block_num"] == current_block_num:
                if i + 1 < len(sorted_blocks):
                    next_b = sorted_blocks[i + 1]
                    scale = tab.renderer._scale
                    y_offset = tab.renderer._page_y_offsets[page_num] if page_num < len(tab.renderer._page_y_offsets) else 0
                    click_pos = QPointF(
                        next_b["bbox"][0] * scale,
                        next_b["bbox"][1] * scale + y_offset,
                    )
                    self._enter_block_edit_mode(tab, next_b["block_num"], page_num, click_pos)
                return

    def _update_block_text(self, tab: TabState, page_num: int, block_num: int, text: str):
        block_overlays = tab.renderer.overlay_manager.get_block_overlays(page_num, block_num)
        lines = text.split("\n")
        for i, ov in enumerate(block_overlays):
            if i < len(lines):
                ov.span_text = lines[i]
            else:
                ov.span_text = ""
        self._on_dirty_changed(tab.edit_tracker.is_dirty)

    def _copy_selection(self):
        tab = self._tab_manager.active_tab()
        if not tab or tab.active_edit is not None:
            return
        text = tab.selection_manager.selected_text()
        if text:
            QApplication.clipboard().setText(text)
            self._status_bar.showMessage(f"Copied {len(text)} characters", 2000)
```

- [ ] **Step 10: Update drag-drop, wheel zoom, config, and close methods**

Replace remaining methods:

```python
    # --- Drag and drop ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_file(Path(path))
                return

    # --- Wheel zoom ---
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            tab = self._tab_manager.active_tab()
            if not tab:
                super().wheelEvent(event)
                return
            delta = event.angleDelta().y()
            current = tab.renderer.view.transform().m11() * 100
            if delta > 0:
                new_zoom = min(300, current + 10)
            else:
                new_zoom = max(50, current - 10)
            tab.renderer.set_zoom(int(new_zoom))
            event.accept()
        else:
            super().wheelEvent(event)

    # --- Config persistence ---
    def _schedule_config_save(self):
        self._save_timer.start()

    def _save_config(self):
        self._config.window_width = self.width()
        self._config.window_height = self.height()
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.display_mode = self._theme_engine.display_mode
        self._config.sidebar_collapsed = self._sidebar.is_collapsed()
        tab = self._tab_manager.active_tab()
        if tab:
            self._config.zoom_level = int(tab.renderer.view.transform().m11() * 100)
        save_config(self._config, CONFIG_PATH)

    def closeEvent(self, event):
        # Check all tabs for unsaved edits
        for i in range(self._tab_manager.count()):
            tab = self._tab_manager.tab_at(i)
            if tab and tab.edit_tracker.is_dirty:
                reply = QMessageBox.question(
                    self, "Unsaved Changes",
                    f"Save changes to {tab.file_path.name if tab.file_path else 'untitled'}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if reply == QMessageBox.StandardButton.Yes:
                    self._save_tab(tab)

        self._save_config()
        for i in range(self._tab_manager.count()):
            tab = self._tab_manager.tab_at(i)
            if tab:
                tab.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_file(Path(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 11: Run the app manually to verify basic functionality**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python main.py`
Expected: App launches with empty state, tab bar visible with + button, sidebar visible on right, toolbar has hamburger menu.

Test: Open a PDF via Ctrl+O. Verify tab appears, PDF renders, sidebar shows the file.

- [ ] **Step 12: Run existing tests**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/ -v --timeout=30`
Expected: Tests pass (some may need minor fixes due to the refactor — fix any failures here)

- [ ] **Step 13: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add main.py
git commit -m "feat: rewrite MainWindow for multi-tab + library sidebar integration"
```

---

### Task 6: Add Single-Instance Support

**Files:**
- Modify: `main.py` (the `main()` function)

- [ ] **Step 1: Implement single-instance check using a named socket**

Update the `main()` function in `main.py`:

```python
import socket
import threading


_LOCK_PORT = 47831  # Arbitrary port for single-instance lock


def _send_to_running_instance(file_path: str) -> bool:
    """Try to send a file path to an already-running instance. Returns True if successful."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(("127.0.0.1", _LOCK_PORT))
        sock.sendall(file_path.encode("utf-8"))
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def _start_listener(window):
    """Listen for file paths from new instances and open them as tabs."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", _LOCK_PORT))
    except OSError:
        return  # Port already in use
    server.listen(5)
    server.settimeout(1.0)

    while True:
        try:
            conn, _ = server.accept()
            data = conn.recv(4096).decode("utf-8").strip()
            if data:
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    window, "open_file_from_external",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, data),
                )
            conn.close()
        except socket.timeout:
            continue
        except OSError:
            break


def main():
    file_arg = sys.argv[1] if len(sys.argv) > 1 else ""

    # Single-instance check
    if file_arg and _send_to_running_instance(file_arg):
        sys.exit(0)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Start listener for future instances
    listener = threading.Thread(target=_start_listener, args=(window,), daemon=True)
    listener.start()

    if file_arg:
        window.open_file(Path(file_arg))
    sys.exit(app.exec())
```

Add this slot to `MainWindow`:

```python
from PySide6.QtCore import Slot

    @Slot(str)
    def open_file_from_external(self, path_str: str):
        """Called from the socket listener when another instance sends a file path."""
        self.open_file(Path(path_str))
        self.raise_()
        self.activateWindow()
```

- [ ] **Step 2: Test manually**

Run two instances:
1. `venv/Scripts/python main.py pdf_input/product_plan.pdf`
2. In another terminal: `venv/Scripts/python main.py pdf_input/product_plan.pdf`

Expected: Second instance should not open a new window — the first window should activate and switch to the file's tab (or show it's already open).

- [ ] **Step 3: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add main.py
git commit -m "feat: add single-instance support via localhost socket"
```

---

### Task 7: Create App Icon

**Files:**
- Create: `icon.ico`
- Create: `create_icon.py` (utility script, can be deleted after)

- [ ] **Step 1: Create a simple app icon using Python**

Create `create_icon.py`:

```python
"""Generate a simple PDF viewer icon as .ico file."""

from PIL import Image, ImageDraw, ImageFont

sizes = [16, 32, 48, 256]
images = []

for size in sizes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Document shape — rounded rect with fold
    margin = size // 8
    fold = size // 4
    x0, y0 = margin, margin
    x1, y1 = size - margin, size - margin

    # Main body
    draw.rectangle([x0, y0 + fold, x1, y1], fill=(41, 42, 66), outline=(100, 100, 180), width=max(1, size // 32))

    # Top part (without fold corner)
    draw.rectangle([x0, y0, x1 - fold, y0 + fold], fill=(41, 42, 66), outline=(100, 100, 180), width=max(1, size // 32))

    # Fold triangle
    draw.polygon([(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)], fill=(60, 62, 90), outline=(100, 100, 180))

    # "PDF" text
    if size >= 32:
        try:
            font_size = size // 4
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        text = "PDF"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2
        ty = y0 + fold + (y1 - y0 - fold - th) // 2
        draw.text((tx, ty), text, fill=(180, 190, 255), font=font)

    images.append(img)

images[0].save("icon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
print("Created icon.ico")
```

- [ ] **Step 2: Run the icon generator**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/pip install Pillow && venv/Scripts/python create_icon.py`
Expected: `icon.ico` created in project root

- [ ] **Step 3: Set the icon in main.py**

In `MainWindow.__init__`, after `self.setWindowTitle("PDF Viewer")`, add:

```python
        # Set app icon
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(icon_path)))
            QApplication.instance().setWindowIcon(QIcon(str(icon_path)))
```

- [ ] **Step 4: Clean up and commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
rm create_icon.py
git add icon.ico main.py
git commit -m "feat: add app icon for window and taskbar"
```

---

### Task 8: PyInstaller Build Setup

**Files:**
- Create: `PDFViewer.spec`
- Create: `build.bat`

- [ ] **Step 1: Install PyInstaller**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/pip install pyinstaller`

- [ ] **Step 2: Create the .spec file**

Create `PDFViewer.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('fonts', 'fonts'),
        ('icon.ico', '.'),
    ],
    hiddenimports=['fitz', 'fitz.fitz'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDFViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDFViewer',
)
```

- [ ] **Step 3: Create the build script**

Create `build.bat`:

```batch
@echo off
echo Building PDF Viewer...
cd /d "%~dp0"
venv\Scripts\pyinstaller PDFViewer.spec --noconfirm
echo.
if exist "dist\PDFViewer\PDFViewer.exe" (
    echo Build successful! Output: dist\PDFViewer\
) else (
    echo Build FAILED.
)
pause
```

- [ ] **Step 4: Run the build**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && cmd.exe /c build.bat`
Expected: Build completes, `dist/PDFViewer/PDFViewer.exe` exists

- [ ] **Step 5: Test the built exe**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && dist/PDFViewer/PDFViewer.exe`
Expected: App launches from the built exe, all features work

- [ ] **Step 6: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add PDFViewer.spec build.bat
git commit -m "feat: add PyInstaller build configuration"
```

---

### Task 9: Inno Setup Installer

**Files:**
- Create: `installer.iss`

- [ ] **Step 1: Create the Inno Setup script**

Create `installer.iss`:

```iss
; Inno Setup Script for PDF Viewer

[Setup]
AppName=PDF Viewer
AppVersion=1.0
AppPublisher=Noah
DefaultDirName={autopf}\PDFViewer
DefaultGroupName=PDF Viewer
OutputDir=installer_output
OutputBaseFilename=PDFViewer_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\PDFViewer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "fileassoc"; Description: "Associate .pdf files with PDF Viewer"; GroupDescription: "File associations:"

[Files]
Source: "dist\PDFViewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Viewer"; Filename: "{app}\PDFViewer.exe"
Name: "{group}\Uninstall PDF Viewer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PDF Viewer"; Filename: "{app}\PDFViewer.exe"; Tasks: desktopicon

[Registry]
; File association (optional — only if user checks the box)
Root: HKCR; Subkey: ".pdf"; ValueType: string; ValueName: ""; ValueData: "PDFViewer.PDF"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PDFViewer.exe,0"; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PDFViewer.exe"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\PDFViewer.exe"; Description: "Launch PDF Viewer"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add installer.iss
git commit -m "feat: add Inno Setup installer script"
```

- [ ] **Step 3: Build the installer (optional — requires Inno Setup installed)**

If Inno Setup is installed, run:
```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```
Expected: `installer_output/PDFViewer_Setup.exe` created

---

### Task 10: Final Integration Test & Cleanup

- [ ] **Step 1: Run all tests**

Run: `cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer && venv/Scripts/python -m pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 2: Manual smoke test checklist**

Run the app and verify:
- [ ] App opens with empty state and sidebar
- [ ] Open a PDF — tab appears, renders correctly, sidebar updates
- [ ] Open a second PDF — new tab, can switch between them
- [ ] Ctrl+W closes a tab
- [ ] Ctrl+Tab cycles tabs
- [ ] Close tab with unsaved edits — prompts to save
- [ ] Hamburger menu shows all actions
- [ ] Theme change applies to all tabs
- [ ] Search works within active tab
- [ ] Double-click text editing works
- [ ] Drag-drop a PDF opens it
- [ ] Sidebar collapse/expand works, state persists
- [ ] Library shows all opened PDFs with thumbnails
- [ ] Click library card opens PDF or switches to tab
- [ ] Right-click library card → Remove from Library works
- [ ] Ctrl+\ toggles sidebar

- [ ] **Step 3: Add dist/, build/, and installer_output/ to .gitignore**

Append to `.gitignore`:

```
dist/
build/
installer_output/
*.pyc
__pycache__/
.superpowers/
```

- [ ] **Step 4: Final commit**

```bash
cd C:/Users/Noah/Documents/Tool_Projects/PDFViewer
git add .gitignore
git commit -m "chore: add build output directories to gitignore"
```
