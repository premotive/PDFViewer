"""Entry point: QApplication, MainWindow, tabs, sidebar, shortcuts, integration."""

import sys
import os
import socket
import tempfile
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QStatusBar, QGraphicsTextItem, QGraphicsRectItem,
    QLabel, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF, QPointF, Slot
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
        return
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Migrate old config if needed
        old_config = Path(__file__).parent / "config.json"
        if old_config.exists() and not CONFIG_PATH.exists():
            import shutil
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_config, CONFIG_PATH)

        self._config = load_config(CONFIG_PATH)
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_config)

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

    @property
    def toolbar(self) -> ToolBar:
        return self._toolbar

    @property
    def search_bar(self) -> SearchBar:
        return self._search_bar

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self._toolbar = ToolBar(self)
        self.addToolBar(self._toolbar)

        # Tab manager
        self._tab_manager = TabManager(theme_engine=self._theme_engine)

        # Search bar
        self._search_bar = SearchBar()

        # Content area: tab views + sidebar
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left side: tabs + search + content
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._tab_manager.tab_bar)
        left_layout.addWidget(self._search_bar)
        left_layout.addWidget(self._tab_manager._stack)

        # Empty state label
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
        tab = self._tab_manager.active_tab()
        if tab:
            getattr(tab.renderer, method)(*args)

    def _active_page_count(self) -> int:
        tab = self._tab_manager.active_tab()
        return tab.renderer.page_count if tab else 0

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

    # --- File operations ---

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

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", str(Path.home()), "PDF Files (*.pdf)")
        if path:
            self.open_file(Path(path))

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

    # --- Tab navigation ---

    def _on_tab_changed(self, index: int):
        tab = self._tab_manager.active_tab()
        if tab is None:
            return
        self._update_title()
        self._update_page_info(tab)
        self._toolbar.set_dirty(tab.edit_tracker.is_dirty)
        self._toolbar.connect_undo_stack(tab.undo_stack)
        self._clear_search_highlights()

    def _close_tab(self, index: int):
        tab = self._tab_manager.tab_at(index)
        if tab is None:
            return
        if tab.edit_tracker.is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to {tab.file_path.name if tab.file_path else 'untitled'}?",
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
        if 0 <= idx < self._tab_manager.count():
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
        has_tabs = self._tab_manager.count() > 0
        self._empty_label.setVisible(not has_tabs)
        self._tab_manager._stack.setVisible(has_tabs)

    def _update_page_info(self, tab: TabState):
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

    # --- Title ---

    def _on_dirty_changed(self, dirty: bool):
        self._toolbar.set_dirty(dirty)
        self._update_title(dirty)

    def _update_title(self, dirty: bool | None = None):
        tab = self._tab_manager.active_tab()
        name = tab.file_path.name if tab and tab.file_path else ""
        is_dirty = dirty if dirty is not None else (tab.edit_tracker.is_dirty if tab else False)
        prefix = "* " if is_dirty else ""
        self.setWindowTitle(f"{prefix}{name} — PDF Viewer" if name else "PDF Viewer")
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

    @Slot(str)
    def open_file_from_external(self, path_str: str):
        """Called from the socket listener when another instance sends a file path."""
        self.open_file(Path(path_str))
        self.raise_()
        self.activateWindow()


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


if __name__ == "__main__":
    main()
