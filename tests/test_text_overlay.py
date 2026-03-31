from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont
from text_overlay import SpanOverlay, OverlayManager


def test_span_overlay_creation(qapp):
    scene = QGraphicsScene()
    span_data = {
        "text": "Hello World", "bbox": (72, 60, 200, 80), "font": "Helvetica",
        "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0,
    }
    overlay = SpanOverlay(span_data, scale=150 / 72.0, page_num=0)
    scene.addItem(overlay)
    assert overlay.span_text == "Hello World"
    assert overlay.page_num == 0


def test_span_overlay_invisible_by_default(qapp):
    scene = QGraphicsScene()
    span_data = {
        "text": "Test", "bbox": (72, 60, 200, 80), "font": "Helvetica",
        "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0,
    }
    overlay = SpanOverlay(span_data, scale=150 / 72.0, page_num=0)
    scene.addItem(overlay)
    overlay.set_faithful_mode()
    assert overlay.opacity() == 0.0


def test_span_overlay_visible_in_reading_mode(qapp):
    scene = QGraphicsScene()
    span_data = {
        "text": "Test", "bbox": (72, 60, 200, 80), "font": "Helvetica",
        "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0,
    }
    overlay = SpanOverlay(span_data, scale=150 / 72.0, page_num=0)
    scene.addItem(overlay)
    overlay.set_reading_mode(QColor("#D4D4D4"))
    assert overlay.opacity() == 1.0


def test_overlay_manager_creates_spans(qapp):
    scene = QGraphicsScene()
    manager = OverlayManager(scene)
    spans = [
        {"text": "First", "bbox": (72, 60, 150, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
        {"text": "Second", "bbox": (72, 90, 150, 110), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 1, "span_num": 0},
    ]
    overlays = manager.create_overlays(spans, scale=150 / 72.0, page_num=0, y_offset=0.0)
    assert len(overlays) == 2


def test_overlay_manager_clear_page(qapp):
    scene = QGraphicsScene()
    manager = OverlayManager(scene)
    spans = [
        {"text": "First", "bbox": (72, 60, 150, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
    ]
    manager.create_overlays(spans, scale=150 / 72.0, page_num=0, y_offset=0.0)
    assert len(manager.get_overlays(0)) == 1
    manager.clear_page(0)
    assert len(manager.get_overlays(0)) == 0


def test_span_overlay_span_id(qapp):
    span_data = {
        "text": "Test", "bbox": (72, 60, 200, 80), "font": "Helvetica",
        "size": 12.0, "color": 0, "flags": 0, "block_num": 1, "line_num": 2, "span_num": 3,
    }
    overlay = SpanOverlay(span_data, scale=1.0, page_num=5)
    assert overlay.span_id == (5, (1, 2, 3))
