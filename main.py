"""Entry point: QApplication, MainWindow, drag-drop, shortcuts, integration."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QStatusBar, QGraphicsTextItem,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF
from PySide6.QtGui import QAction, QKeySequence, QUndoStack

from config import AppConfig, load_config, save_config
from pdf_engine import PDFEngine
from page_renderer import PageRenderer
from text_overlay import SpanOverlay, SelectionManager
from theme_engine import ThemeEngine
from editor import EditTracker, SpanEditCommand
from search import SearchEngine, SearchBar
from toolbar import ToolBar

CONFIG_PATH = Path(__file__).parent / "config.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._config = load_config(CONFIG_PATH)
        self._file_path: Path | None = None
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_config)

        # Core components
        self._theme_engine = ThemeEngine()
        self._theme_engine.set_theme(self._config.theme)
        self._theme_engine.set_display_mode(self._config.display_mode)

        self._main_engine = PDFEngine()
        self._renderer = PageRenderer(main_engine=self._main_engine, theme_engine=self._theme_engine)
        self._edit_tracker = EditTracker()
        self._undo_stack = QUndoStack(self)
        self._search_engine = SearchEngine()
        self._active_edit = None
        self._search_results = []
        self._search_index = -1
        self._search_highlights = []
        self._current_highlight = None
        self._rubber_band_start = None
        self._selection_manager = None  # Initialized after renderer is set up

        # UI setup
        self.setWindowTitle("PDF Viewer")
        self._setup_ui()
        self._setup_shortcuts()
        self._setup_connections()

        self._selection_manager = SelectionManager(
            self._renderer.scene, self._renderer.overlay_manager
        )

        # Restore window geometry
        self.resize(self._config.window_width, self._config.window_height)
        self.move(self._config.window_x, self._config.window_y)

        # Enable drag and drop
        self.setAcceptDrops(True)

    @property
    def renderer(self) -> PageRenderer:
        return self._renderer

    @property
    def toolbar(self) -> ToolBar:
        return self._toolbar

    @property
    def search_bar(self) -> SearchBar:
        return self._search_bar

    def _setup_ui(self):
        # Menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self._toolbar = ToolBar(self)
        self.addToolBar(self._toolbar)

        # Menu bar actions (must be after toolbar creation)
        file_menu.addAction(self._toolbar.open_action)
        file_menu.addAction(self._toolbar.save_action)
        file_menu.addAction(self._toolbar.save_as_action)

        undo_action = self._undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut("Ctrl+Z")
        edit_menu.addAction(undo_action)
        redo_action = self._undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut("Ctrl+Y")
        edit_menu.addAction(redo_action)

        toggle_mode_action = QAction("Toggle Reading/Faithful Mode", self)
        toggle_mode_action.setShortcut("F5")
        toggle_mode_action.triggered.connect(self._theme_engine.toggle_display_mode)
        view_menu.addAction(toggle_mode_action)

        # Search bar
        self._search_bar = SearchBar()
        layout.addWidget(self._search_bar)

        # PDF view
        layout.addWidget(self._renderer.view)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _setup_shortcuts(self):
        # Find
        find_action = QAction("Find", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self._show_search)
        self.addAction(find_action)

        # Copy
        copy_action = QAction("Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self._copy_selection)
        self.addAction(copy_action)

        # Keyboard navigation
        for key, slot in [
            (Qt.Key.Key_Home, lambda: self._renderer.scroll_to_page(0)),
            (Qt.Key.Key_End, lambda: self._renderer.scroll_to_page(self._renderer.page_count - 1)),
        ]:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _setup_connections(self):
        # Toolbar signals
        self._toolbar.open_requested.connect(self._open_dialog)
        self._toolbar.save_requested.connect(self._save)
        self._toolbar.save_as_requested.connect(self._save_as)
        self._toolbar.theme_selected.connect(self._on_theme_selected)
        self._toolbar.bg_color_selected.connect(self._on_bg_color)
        self._toolbar.font_color_selected.connect(self._on_font_color)
        self._toolbar.zoom_selected.connect(self._on_zoom)
        self._toolbar.page_jump_requested.connect(lambda p: self._renderer.scroll_to_page(p - 1))
        self._toolbar.mode_toggle_requested.connect(self._theme_engine.toggle_display_mode)

        # Page changed
        self._renderer.page_changed.connect(lambda p: self._toolbar.set_current_page(p + 1))

        # Search
        self._search_bar.search_requested.connect(self._on_search)
        self._search_bar.next_requested.connect(self._on_search_next)
        self._search_bar.prev_requested.connect(self._on_search_prev)
        self._search_bar.closed.connect(self._clear_search_highlights)

        # Render worker search index signals
        self._renderer._render_worker.search_text_ready.connect(self._on_search_text_ready)
        self._renderer._render_worker.search_index_complete.connect(self._on_search_index_complete)

        # Viewport events for edit mode and selection
        self._renderer.view.viewport().installEventFilter(self)

    def open_file(self, path: Path):
        path = Path(path)
        if not path.exists():
            QMessageBox.warning(self, "Error", f"File not found: {path}")
            return

        if self._edit_tracker.is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes", "Save changes before opening a new file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save()

        # Reset state
        self._edit_tracker.clear()
        self._undo_stack.clear()
        self._search_engine.clear()
        self._search_bar.set_indexing()
        self._clear_search_highlights()

        # Try opening with password retry
        try:
            needs_pass = self._renderer.open_document(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open file: {e}")
            return

        if needs_pass:
            for attempt in range(3):
                password, ok = QInputDialog.getText(
                    self, "Password Required",
                    f"Enter PDF password (attempt {attempt + 1}/3):",
                    QInputDialog.InputMode.TextInput,
                )
                if not ok:
                    return
                needs_pass = self._renderer.open_document(path, password)
                if not needs_pass:
                    break
            else:
                QMessageBox.warning(self, "Error", "Failed to authenticate after 3 attempts.")
                return

        self._file_path = path
        self._update_title()
        self._toolbar.set_page_count(self._renderer.page_count)
        self._toolbar.set_current_page(1)
        self._toolbar.set_dirty(False)
        self._status_bar.showMessage(f"Opened: {path.name}")

        # Check for scanned PDF
        if self._renderer.page_count > 0:
            spans = self._main_engine.extract_spans(0)
            if not spans:
                self._status_bar.showMessage("This PDF is image-based. Text editing is not available.")

        self._config.last_opened_file = str(path)
        self._schedule_config_save()

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", str(Path.home()), "PDF Files (*.pdf)")
        if path:
            self.open_file(Path(path))

    def _save(self):
        if not self._file_path or not self._edit_tracker.is_dirty:
            return
        self._save_to(self._file_path)

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF As", str(Path.home()), "PDF Files (*.pdf)")
        if path:
            self._save_to(Path(path))

    def _save_to(self, path: Path):
        try:
            edits = self._edit_tracker.dirty_edits
            if not edits:
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

            warnings = self._main_engine.save_edits(edits, tmp_path)

            self._main_engine.close()
            self._renderer.close_document()

            bak_path = path.with_suffix(".pdf.bak")
            if path.exists():
                if bak_path.exists():
                    bak_path.unlink()
                path.rename(bak_path)
            tmp_path.rename(path)

            self._renderer.open_document(path)
            self._file_path = path

            if bak_path.exists():
                bak_path.unlink()

            self._edit_tracker.clear()
            self._undo_stack.clear()
            self._toolbar.set_dirty(False)
            self._update_title()

            for w in warnings:
                self._status_bar.showMessage(w, 5000)
            self._status_bar.showMessage(f"Saved: {path.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")

    def _on_dirty_changed(self, dirty: bool):
        self._toolbar.set_dirty(dirty)
        self._update_title(dirty)

    def _update_title(self, dirty: bool | None = None):
        name = self._file_path.name if self._file_path else ""
        is_dirty = dirty if dirty is not None else self._edit_tracker.is_dirty
        prefix = "* " if is_dirty else ""
        self.setWindowTitle(f"{prefix}{name} — PDF Viewer" if name else "PDF Viewer")

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
        if value == "fit_width":
            self._renderer.fit_width()
        elif value == "fit_page":
            self._renderer.fit_page()
        else:
            try:
                self._renderer.set_zoom(int(value))
            except ValueError:
                pass

    # --- Search ---
    def _show_search(self):
        if not self._search_engine.is_ready:
            self._search_bar.set_indexing()
        self._search_bar.show_bar()

    def _on_search_text_ready(self, page_num: int, text: str):
        self._search_engine.set_page_text(page_num, text)

    def _on_search_index_complete(self):
        self._search_engine.mark_ready()
        self._status_bar.showMessage("Search index ready", 2000)

    def _on_search(self, query: str, case_sensitive: bool):
        self._clear_search_highlights()
        if not self._search_engine.is_ready or not query:
            self._search_bar.update_count(0, 0)
            return

        if self._main_engine.is_open and self._main_engine._doc is not None:
            results = self._search_engine.search_with_quads(
                query, self._main_engine._doc, case_sensitive
            )
        else:
            results = self._search_engine.search(query, case_sensitive)
        self._search_results = results
        self._search_index = 0 if results else -1
        self._search_bar.update_count(self._search_index, len(results))
        if results:
            self._jump_to_search_result(0)

    def _on_search_next(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index + 1) % len(self._search_results)
        self._search_bar.update_count(self._search_index, len(self._search_results))
        self._jump_to_search_result(self._search_index)

    def _on_search_prev(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index - 1) % len(self._search_results)
        self._search_bar.update_count(self._search_index, len(self._search_results))
        self._jump_to_search_result(self._search_index)

    def _jump_to_search_result(self, index: int):
        self._clear_search_highlights()
        result = self._search_results[index]
        page_num = result["page"]
        self._renderer.scroll_to_page(page_num)

        # Highlight matches on this page if we have quad data
        if "rect" in result:
            from PySide6.QtWidgets import QGraphicsRectItem
            from PySide6.QtGui import QBrush, QPen, QColor

            scale = self._renderer._scale
            y_offset = self._renderer._page_y_offsets[page_num] if page_num < len(self._renderer._page_y_offsets) else 0

            for i, r in enumerate(self._search_results):
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
                    highlight.setBrush(QBrush(QColor(255, 165, 0, 100)))
                    self._current_highlight = highlight
                else:
                    highlight.setBrush(QBrush(QColor(255, 255, 0, 80)))
                highlight.setZValue(2.5)
                self._renderer.scene.addItem(highlight)
                self._search_highlights.append(highlight)

    def _clear_search_highlights(self):
        for h in self._search_highlights:
            self._renderer.scene.removeItem(h)
        self._search_highlights.clear()
        self._current_highlight = None

    # --- Edit mode ---
    def eventFilter(self, obj, event):
        if obj == self._renderer.view.viewport():
            if event.type() == QEvent.Type.MouseButtonDblClick:
                scene_pos = self._renderer.view.mapToScene(event.position().toPoint())
                self._handle_double_click(scene_pos)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._rubber_band_start = self._renderer.view.mapToScene(event.position().toPoint())
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton and self._rubber_band_start is not None:
                    end = self._renderer.view.mapToScene(event.position().toPoint())
                    rect = QRectF(self._rubber_band_start, end).normalized()
                    if rect.width() > 5 and rect.height() > 5:
                        page_num = self._renderer.current_page()
                        self._selection_manager.select_rect(rect, page_num)
                    self._rubber_band_start = None
        return super().eventFilter(obj, event)

    def _handle_double_click(self, scene_pos):
        page_num = self._renderer.current_page()
        overlays = self._renderer.overlay_manager.get_overlays(page_num)
        for overlay in overlays:
            item_pos = overlay.mapFromScene(scene_pos)
            if overlay.boundingRect().contains(item_pos):
                self._enter_edit_mode(overlay)
                return

    def _enter_edit_mode(self, overlay: SpanOverlay):
        edit_item = QGraphicsTextItem(overlay.span_text)
        edit_item.setFont(overlay.font())
        edit_item.setPos(overlay.pos())
        edit_item.setZValue(overlay.zValue() + 1)
        edit_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        edit_item.setDefaultTextColor(
            self._theme_engine.font_color if self._theme_engine.show_text_overlays else Qt.GlobalColor.black
        )

        self._renderer.scene.addItem(edit_item)
        edit_item.setFocus()
        overlay.hide()

        self._active_edit = {
            "overlay": overlay,
            "edit_item": edit_item,
            "original_text": overlay.span_text,
        }

        # Handle Tab and Escape
        original_key_press = edit_item.keyPressEvent
        def custom_key_press(event):
            if event.key() == Qt.Key.Key_Escape:
                self._exit_edit_mode()
            elif event.key() == Qt.Key.Key_Tab:
                self._exit_edit_mode()
                self._advance_to_next_span(overlay)
            else:
                original_key_press(event)
        edit_item.keyPressEvent = custom_key_press

        edit_item.focusOutEvent = lambda e: self._exit_edit_mode()
        self._status_bar.showMessage("Editing — press Escape to finish")

    def _exit_edit_mode(self):
        if self._active_edit is None:
            return

        edit_data = self._active_edit
        self._active_edit = None

        overlay = edit_data["overlay"]
        edit_item = edit_data["edit_item"]
        original_text = edit_data["original_text"]
        new_text = edit_item.toPlainText()

        self._renderer.scene.removeItem(edit_item)
        overlay.show()

        if new_text != original_text:
            overlay.span_text = new_text
            span_data = overlay.span_data
            cmd = SpanEditCommand(
                tracker=self._edit_tracker,
                span_id=overlay.span_id,
                old_text=original_text,
                new_text=new_text,
                original_rect=span_data["bbox"],
                font=span_data["font"],
                size=span_data["size"],
                color=span_data["color"],
                flags=span_data["flags"],
                text_updater=self._update_span_text,
            )
            self._undo_stack.push(cmd)
            self._on_dirty_changed(self._edit_tracker.is_dirty)

        self._status_bar.showMessage("Ready")

    def _advance_to_next_span(self, current_overlay: SpanOverlay):
        page_num = current_overlay.page_num
        overlays = self._renderer.overlay_manager.get_overlays(page_num)
        sorted_overlays = sorted(
            overlays, key=lambda ov: (ov.span_data["bbox"][1], ov.span_data["bbox"][0])
        )
        for i, ov in enumerate(sorted_overlays):
            if ov.span_id == current_overlay.span_id:
                if i + 1 < len(sorted_overlays):
                    self._enter_edit_mode(sorted_overlays[i + 1])
                return

    def _update_span_text(self, span_id, text):
        page_num = span_id[0]
        for overlay in self._renderer.overlay_manager.get_overlays(page_num):
            if overlay.span_id == span_id:
                overlay.span_text = text
                break
        self._on_dirty_changed(self._edit_tracker.is_dirty)

    def _copy_selection(self):
        if self._active_edit is not None:
            return
        text = self._selection_manager.selected_text()
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
            delta = event.angleDelta().y()
            current = self._renderer.view.transform().m11() * 100
            if delta > 0:
                new_zoom = min(300, current + 10)
            else:
                new_zoom = max(50, current - 10)
            self._renderer.set_zoom(int(new_zoom))
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
        self._config.zoom_level = int(self._renderer.view.transform().m11() * 100)
        save_config(self._config, CONFIG_PATH)

    def closeEvent(self, event):
        if self._edit_tracker.is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes", "Save changes before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save()

        self._save_config()
        self._renderer.close_document()
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
