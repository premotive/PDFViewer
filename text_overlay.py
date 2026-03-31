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
    In reading mode: visible with color adapted for the theme background.
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

    def set_reading_mode(self):
        # Overlays stay invisible — the colour-transformed page image already
        # renders text correctly.  Overlays exist only as hover/click targets.
        self.setOpacity(0.0)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        if not self._is_editing and self.scene() is not None:
            if self._highlight is None:
                scene_rect = self.mapRectToScene(self.boundingRect())
                self._highlight = QGraphicsRectItem(scene_rect)
                self._highlight.setPen(QPen(Qt.PenStyle.NoPen))
                self._highlight.setZValue(1.5)
                self.scene().addItem(self._highlight)
            self._highlight.setBrush(QBrush(QColor(100, 150, 255, 70)))
            self._highlight.show()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self._highlight:
            self._highlight.hide()
        super().hoverLeaveEvent(event)

    def cleanup_highlight(self):
        """Remove the hover highlight from the scene."""
        if self._highlight and self.scene() is not None:
            self.scene().removeItem(self._highlight)
            self._highlight = None


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

    def get_block_overlays(self, page_num: int, block_num: int) -> list[SpanOverlay]:
        """Return all overlays on a page that belong to the given block number."""
        return [
            ov for ov in self._overlays.get(page_num, [])
            if ov.span_data["block_num"] == block_num
        ]

    def clear_page(self, page_num: int):
        for overlay in self._overlays.pop(page_num, []):
            overlay.cleanup_highlight()
            self._scene.removeItem(overlay)

    def clear_all(self):
        for page_num in list(self._overlays.keys()):
            self.clear_page(page_num)

    def set_faithful_mode(self):
        for overlays in self._overlays.values():
            for overlay in overlays:
                overlay.set_faithful_mode()

    def set_reading_mode(self):
        for overlays in self._overlays.values():
            for overlay in overlays:
                overlay.set_reading_mode()

    def find_overlay_at(self, page_num: int, scene_pos) -> SpanOverlay | None:
        for overlay in self._overlays.get(page_num, []):
            if overlay.contains(overlay.mapFromScene(scene_pos)):
                return overlay
        return None


class SelectionManager:
    """Handles rubber-band text selection and copy-to-clipboard."""

    def __init__(self, scene: QGraphicsScene, overlay_manager: OverlayManager):
        self._scene = scene
        self._overlay_mgr = overlay_manager
        self._selected: list[SpanOverlay] = []
        self._highlight_rects: list[QGraphicsRectItem] = []

    def select_rect(self, rect: QRectF, page_num: int):
        """Select all spans on page_num whose bboxes intersect the given rect."""
        self.clear_selection()
        overlays = self._overlay_mgr.get_overlays(page_num)
        for overlay in overlays:
            item_rect = overlay.mapRectToScene(overlay.boundingRect())
            if rect.intersects(item_rect):
                self._selected.append(overlay)
                highlight = QGraphicsRectItem(item_rect)
                highlight.setPen(QPen(Qt.PenStyle.NoPen))
                highlight.setBrush(QBrush(QColor(80, 130, 255, 90)))
                highlight.setZValue(3)
                self._scene.addItem(highlight)
                self._highlight_rects.append(highlight)

    def clear_selection(self):
        """Remove all selection highlights."""
        for rect in self._highlight_rects:
            self._scene.removeItem(rect)
        self._highlight_rects.clear()
        self._selected.clear()

    def selected_text(self) -> str:
        """Return concatenated text of selected spans, sorted by y then x position."""
        if not self._selected:
            return ""
        sorted_spans = sorted(
            self._selected,
            key=lambda ov: (ov.span_data["bbox"][1], ov.span_data["bbox"][0]),
        )
        return "\n".join(ov.span_text for ov in sorted_spans)

    def has_selection(self) -> bool:
        return len(self._selected) > 0
