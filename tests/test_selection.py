from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import QRectF
from text_overlay import SpanOverlay, OverlayManager, SelectionManager


def test_selection_manager_creation(qapp):
    scene = QGraphicsScene()
    overlay_mgr = OverlayManager(scene)
    sel_mgr = SelectionManager(scene, overlay_mgr)
    assert sel_mgr.selected_text() == ""


def test_select_spans_by_rect(qapp):
    scene = QGraphicsScene()
    overlay_mgr = OverlayManager(scene)
    spans = [
        {"text": "First span", "bbox": (72, 60, 150, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
        {"text": "Second span", "bbox": (72, 90, 160, 110), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 1, "span_num": 0},
        {"text": "Far away", "bbox": (400, 400, 500, 420), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 1, "line_num": 0, "span_num": 0},
    ]
    overlay_mgr.create_overlays(spans, scale=1.0, page_num=0, y_offset=0.0)
    sel_mgr = SelectionManager(scene, overlay_mgr)

    sel_mgr.select_rect(QRectF(50, 50, 200, 80), page_num=0)
    text = sel_mgr.selected_text()
    assert "First span" in text
    assert "Second span" in text
    assert "Far away" not in text


def test_clear_selection(qapp):
    scene = QGraphicsScene()
    overlay_mgr = OverlayManager(scene)
    spans = [
        {"text": "Some text", "bbox": (72, 60, 150, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
    ]
    overlay_mgr.create_overlays(spans, scale=1.0, page_num=0, y_offset=0.0)
    sel_mgr = SelectionManager(scene, overlay_mgr)
    sel_mgr.select_rect(QRectF(50, 50, 200, 80), page_num=0)
    assert sel_mgr.selected_text() != ""
    sel_mgr.clear_selection()
    assert sel_mgr.selected_text() == ""


def test_selected_text_sorted_by_position(qapp):
    scene = QGraphicsScene()
    overlay_mgr = OverlayManager(scene)
    spans = [
        {"text": "Bottom line", "bbox": (72, 100, 200, 120), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 1, "span_num": 0},
        {"text": "Top line", "bbox": (72, 60, 200, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
    ]
    overlay_mgr.create_overlays(spans, scale=1.0, page_num=0, y_offset=0.0)
    sel_mgr = SelectionManager(scene, overlay_mgr)
    sel_mgr.select_rect(QRectF(50, 50, 200, 100), page_num=0)
    text = sel_mgr.selected_text()
    assert text.index("Top line") < text.index("Bottom line")
