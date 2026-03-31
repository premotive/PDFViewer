"""Text span overlay items for the PDF viewer."""

from PySide6.QtWidgets import (
    QGraphicsSimpleTextItem, QGraphicsTextItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsItem,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPen, QBrush


class SpanOverlay(QGraphicsSimpleTextItem):
    """A text span overlay positioned on top of the PDF pixmap.

    In faithful mode: fully invisible, acts as hover/click target.
    In reading mode: visible with theme's font color.
    """

    def __init__(self, span_data: dict, scale: float, page_num: int, parent=None):
        super().__init__(span_data["text"], parent)
        self._span_data = span_data
        self._page_num = page_num
        self._scale = scale
        self._original_text = span_data["text"]
        self._current_text = span_data["text"]
        self._is_editing = False

        # Position at scaled PDF coordinates
        bbox = span_data["bbox"]
        self.setPos(bbox[0] * scale, bbox[1] * scale)

        # Set font
        font = QFont()
        font.setPointSizeF(span_data["size"] * scale * 0.75)
        flags = span_data["flags"]
        if flags & (1 << 4):
            font.setBold(True)
        if flags & (1 << 1):
            font.setItalic(True)
        if flags & (1 << 3):
            font.setFamily("Courier")
        self.setFont(font)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._highlight = None
        self.setOpacity(0.0)  # Start invisible (faithful mode default)

    @property
    def span_text(self) -> str:
        return self._current_text

    @span_text.setter
    def span_text(self, text: str):
        self._current_text = text
        self.setText(text)

    @property
    def page_num(self) -> int:
        return self._page_num

    @property
    def span_id(self) -> tuple:
        return (self._page_num, (self._span_data["block_num"], self._span_data["line_num"], self._span_data["span_num"]))

    @property
    def original_text(self) -> str:
        return self._original_text

    @property
    def span_data(self) -> dict:
        return self._span_data

    def set_faithful_mode(self):
        self.setOpacity(0.0)
        self.setAcceptHoverEvents(True)

    def set_reading_mode(self, font_color: QColor):
        self.setOpacity(1.0)
        self.setBrush(QBrush(font_color))
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        if not self._is_editing:
            if self._highlight is None:
                self._highlight = QGraphicsRectItem(self.boundingRect(), self)
                self._highlight.setPen(QPen(Qt.PenStyle.NoPen))
            self._highlight.setBrush(QBrush(QColor(100, 150, 255, 40)))
            self._highlight.show()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self._highlight:
            self._highlight.hide()
        super().hoverLeaveEvent(event)


class OverlayManager:
    """Manages span overlays across multiple pages."""

    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._overlays: dict[int, list[SpanOverlay]] = {}

    def create_overlays(self, spans: list[dict], scale: float, page_num: int, y_offset: float) -> list[SpanOverlay]:
        overlays = []
        for span_data in spans:
            overlay = SpanOverlay(span_data, scale=scale, page_num=page_num)
            overlay.moveBy(0, y_offset)
            overlay.setZValue(2)
            self._scene.addItem(overlay)
            overlays.append(overlay)
        self._overlays[page_num] = overlays
        return overlays

    def get_overlays(self, page_num: int) -> list[SpanOverlay]:
        return self._overlays.get(page_num, [])

    def clear_page(self, page_num: int):
        for overlay in self._overlays.pop(page_num, []):
            self._scene.removeItem(overlay)

    def clear_all(self):
        for page_num in list(self._overlays.keys()):
            self.clear_page(page_num)

    def set_faithful_mode(self):
        for overlays in self._overlays.values():
            for overlay in overlays:
                overlay.set_faithful_mode()

    def set_reading_mode(self, font_color: QColor):
        for overlays in self._overlays.values():
            for overlay in overlays:
                overlay.set_reading_mode(font_color)

    def find_overlay_at(self, page_num: int, scene_pos) -> SpanOverlay | None:
        for overlay in self._overlays.get(page_num, []):
            if overlay.contains(overlay.mapFromScene(scene_pos)):
                return overlay
        return None
