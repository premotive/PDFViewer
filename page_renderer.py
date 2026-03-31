"""QGraphicsScene management, page layout, lazy loading, and render queue."""

from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsSimpleTextItem,
)
from PySide6.QtCore import Qt, QRectF, QTimer, Signal, QObject
from PySide6.QtGui import QPixmap, QImage, QColor, QBrush, QPen, QFont, QTransform

from pdf_engine import PDFEngine
from render_worker import RenderWorker, RenderRequest, RenderResult
from text_overlay import OverlayManager, SpanOverlay
from theme_engine import ThemeEngine

PAGE_GAP = 20.0


class PageRenderer(QObject):
    page_changed = Signal(int)

    def __init__(self, main_engine: PDFEngine, theme_engine: ThemeEngine | None = None, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._theme = theme_engine or ThemeEngine()
        self._overlay_manager = OverlayManager(self._scene)
        self._main_engine = main_engine  # Shared with MainWindow
        self._render_worker = RenderWorker()

        self._page_rects: list = []
        self._page_y_offsets: list[float] = []
        self._total_height: float = 0.0
        self._base_dpi: int = 150
        self._dpi: int = 150
        self._scale: float = 150.0 / 72.0

        self._loaded_pages: dict[int, dict] = {}
        self._placeholder_items: dict[int, QGraphicsRectItem] = {}
        self._generation: int = 0

        self._scroll_timer = QTimer()
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(50)
        self._scroll_timer.timeout.connect(self._on_scroll_settle)

        self._zoom_timer = QTimer()
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(300)
        self._zoom_timer.timeout.connect(self._on_zoom_settle)

        self._render_worker.result_ready.connect(self._on_render_result)
        self._theme.theme_changed.connect(self._apply_theme)
        self._theme.mode_changed.connect(self._apply_mode)

        if self._view.verticalScrollBar():
            self._view.verticalScrollBar().valueChanged.connect(self._on_scroll)

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def view(self) -> QGraphicsView:
        return self._view

    @property
    def page_count(self) -> int:
        return len(self._page_rects)

    @property
    def total_height(self) -> float:
        return self._total_height

    @property
    def page_y_offsets(self) -> list[float]:
        return list(self._page_y_offsets)

    @property
    def overlay_manager(self) -> OverlayManager:
        return self._overlay_manager

    @property
    def theme(self) -> ThemeEngine:
        return self._theme

    def update_dpi_for_screen(self):
        screen = self._view.screen()
        if screen:
            dpr = screen.devicePixelRatio()
            self._dpi = int(self._base_dpi * dpr)
            self._scale = self._dpi / 72.0

    def open_document(self, path: Path, password: str | None = None) -> bool:
        self.close_document()

        needs_pass = self._main_engine.open(path)
        if needs_pass:
            if password:
                if not self._main_engine.authenticate(password):
                    self._main_engine.close()
                    return True
            else:
                return True

        self._page_rects = self._main_engine.page_rects
        self._compute_layout()

        max_width = max((r.width * self._scale for r in self._page_rects), default=0)
        self._scene.setSceneRect(0, 0, max_width + 40, self._total_height)

        self._create_placeholders()

        self._render_worker.open_document(path, password)
        self._render_worker.start()
        self._render_worker.request_search_index()
        self._request_visible_pages()

        return False

    def close_document(self):
        if self._render_worker.isRunning():
            self._render_worker.stop()
            self._render_worker.wait()

        self._overlay_manager.clear_all()
        self._scene.clear()
        self._loaded_pages.clear()
        self._placeholder_items.clear()
        self._main_engine.close()
        self._page_rects = []
        self._page_y_offsets = []
        self._total_height = 0.0
        self._generation = 0

    def _compute_layout(self):
        self._page_y_offsets = []
        y = 0.0
        for rect in self._page_rects:
            self._page_y_offsets.append(y)
            y += rect.height * self._scale + PAGE_GAP
        self._total_height = y - PAGE_GAP if self._page_rects else 0.0

    def _create_placeholders(self):
        for i, rect in enumerate(self._page_rects):
            w = rect.width * self._scale
            h = rect.height * self._scale
            y = self._page_y_offsets[i]

            placeholder = QGraphicsRectItem(0, y, w, h)
            placeholder.setBrush(QBrush(QColor(230, 230, 230)))
            placeholder.setPen(QPen(QColor(200, 200, 200)))
            placeholder.setZValue(-1)
            self._scene.addItem(placeholder)
            self._placeholder_items[i] = placeholder

            label = QGraphicsSimpleTextItem(f"Page {i + 1}")
            label.setFont(QFont("Arial", 14))
            label.setBrush(QBrush(QColor(150, 150, 150)))
            label.setPos(w / 2 - 30, y + h / 2 - 10)
            label.setParentItem(placeholder)

    def visible_page_range(self, viewport_rect: QRectF | None = None) -> list[int]:
        if viewport_rect is None:
            viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()

        visible = []
        buffer_pages = 2
        for i, y_off in enumerate(self._page_y_offsets):
            page_h = self._page_rects[i].height * self._scale
            page_top = y_off
            page_bottom = y_off + page_h
            if page_bottom >= viewport_rect.top() and page_top <= viewport_rect.bottom():
                visible.append(i)

        if visible:
            first = max(0, visible[0] - buffer_pages)
            last = min(self.page_count - 1, visible[-1] + buffer_pages)
            return list(range(first, last + 1))
        return []

    def current_page(self) -> int:
        if not self._page_y_offsets:
            return 0
        viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
        center_y = viewport_rect.center().y()
        for i, y_off in enumerate(self._page_y_offsets):
            page_h = self._page_rects[i].height * self._scale
            if y_off <= center_y <= y_off + page_h:
                return i
        return 0

    def scroll_to_page(self, page_num: int):
        if 0 <= page_num < len(self._page_y_offsets):
            y = self._page_y_offsets[page_num]
            self._view.centerOn(self._view.sceneRect().width() / 2, y)

    def set_zoom(self, zoom_percent: int):
        factor = zoom_percent / 100.0
        self._view.setTransform(QTransform.fromScale(factor, factor))
        self._zoom_timer.start()

    def fit_width(self):
        if not self._page_rects:
            return
        page_w = self._page_rects[self.current_page()].width * self._scale
        viewport_w = self._view.viewport().width()
        factor = viewport_w / page_w * 0.95
        self._view.setTransform(QTransform.fromScale(factor, factor))

    def fit_page(self):
        if not self._page_rects:
            return
        cp = self.current_page()
        page_w = self._page_rects[cp].width * self._scale
        page_h = self._page_rects[cp].height * self._scale
        viewport_w = self._view.viewport().width()
        viewport_h = self._view.viewport().height()
        factor = min(viewport_w / page_w, viewport_h / page_h) * 0.95
        self._view.setTransform(QTransform.fromScale(factor, factor))

    def _on_scroll(self):
        self._scroll_timer.start()

    def _on_scroll_settle(self):
        self._request_visible_pages()
        self._unload_distant_pages()
        self.page_changed.emit(self.current_page())

    def _on_zoom_settle(self):
        self._request_visible_pages()

    def _request_visible_pages(self):
        self._generation += 1
        self._render_worker.set_current_generation(self._generation)
        for page_num in self.visible_page_range():
            if page_num not in self._loaded_pages:
                self._render_worker.submit(
                    RenderRequest(page_num=page_num, dpi=self._dpi, generation=self._generation)
                )

    def _unload_distant_pages(self):
        visible = set(self.visible_page_range())
        buffer = 5
        if visible:
            keep_range = set(range(max(0, min(visible) - buffer), min(self.page_count, max(visible) + buffer + 1)))
        else:
            keep_range = set()
        for page_num in [p for p in self._loaded_pages if p not in keep_range]:
            self._unload_page(page_num)

    def _unload_page(self, page_num: int):
        page_data = self._loaded_pages.pop(page_num, None)
        if page_data:
            if page_data.get("pixmap_item"):
                self._scene.removeItem(page_data["pixmap_item"])
            if page_data.get("tint_item"):
                self._scene.removeItem(page_data["tint_item"])
        self._overlay_manager.clear_page(page_num)
        if page_num in self._placeholder_items:
            self._placeholder_items[page_num].show()

    def _on_render_result(self, result: RenderResult):
        if result.generation < self._generation:
            return

        # Guard: document may have been closed or page out of range
        if not self._page_rects or result.page_num >= len(self._page_rects):
            return

        # Guard: page may have already been loaded by a duplicate result
        if result.page_num in self._loaded_pages:
            return

        if result.error:
            if result.page_num in self._placeholder_items:
                placeholder = self._placeholder_items[result.page_num]
                for child in placeholder.childItems():
                    child.setParentItem(None)
                    self._scene.removeItem(child)
                label = QGraphicsSimpleTextItem(f"Page {result.page_num + 1} could not be rendered")
                label.setFont(QFont("Arial", 11))
                label.setBrush(QBrush(QColor(200, 50, 50)))
                label.setParentItem(placeholder)
            return

        page_num = result.page_num
        y_offset = self._page_y_offsets[page_num]

        if page_num in self._placeholder_items:
            self._placeholder_items[page_num].hide()

        pixmap = QPixmap.fromImage(result.image)
        pixmap_item = QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, y_offset)
        pixmap_item.setZValue(0)
        self._scene.addItem(pixmap_item)

        w = self._page_rects[page_num].width * self._scale
        h = self._page_rects[page_num].height * self._scale
        tint_item = QGraphicsRectItem(0, y_offset, w, h)
        tint_item.setPen(QPen(Qt.PenStyle.NoPen))
        tint_item.setBrush(QBrush(self._theme.bg_color))
        tint_item.setZValue(1)
        tint_item.setVisible(self._theme.show_tint)
        self._scene.addItem(tint_item)

        self._loaded_pages[page_num] = {"pixmap_item": pixmap_item, "tint_item": tint_item}

        if result.spans:
            overlays = self._overlay_manager.create_overlays(
                result.spans, scale=self._scale, page_num=page_num, y_offset=y_offset,
            )
            if self._theme.show_text_overlays:
                for ov in overlays:
                    ov.set_reading_mode(self._theme.font_color)
            else:
                for ov in overlays:
                    ov.set_faithful_mode()

    def _apply_theme(self):
        self._scene.blockSignals(True)
        bg = self._theme.bg_color
        font = self._theme.font_color
        for page_data in self._loaded_pages.values():
            tint = page_data.get("tint_item")
            if tint:
                tint.setBrush(QBrush(bg))
        if self._theme.show_text_overlays:
            self._overlay_manager.set_reading_mode(font)
        self._scene.blockSignals(False)
        self._scene.update()

    def _apply_mode(self):
        self._scene.blockSignals(True)
        show_tint = self._theme.show_tint
        for page_data in self._loaded_pages.values():
            tint = page_data.get("tint_item")
            if tint:
                tint.setVisible(show_tint)
        if self._theme.show_text_overlays:
            self._overlay_manager.set_reading_mode(self._theme.font_color)
        else:
            self._overlay_manager.set_faithful_mode()
        self._scene.blockSignals(False)
        self._scene.update()
