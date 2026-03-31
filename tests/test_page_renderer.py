from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import QRectF, QEventLoop, QTimer
from page_renderer import PageRenderer
from pdf_engine import PDFEngine


def test_page_renderer_creation(qapp):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    assert renderer.scene is not None
    assert renderer.view is not None
    assert renderer.page_count == 0


def test_open_document(qapp, sample_pdf):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    renderer.open_document(sample_pdf)
    assert renderer.page_count == 1
    assert renderer.total_height > 0
    renderer.close_document()


def test_open_multipage_document(qapp, multipage_pdf):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    renderer.open_document(multipage_pdf)
    assert renderer.page_count == 10
    assert renderer.total_height > 0
    renderer.close_document()


def test_page_y_offsets(qapp, multipage_pdf):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    renderer.open_document(multipage_pdf)
    offsets = renderer.page_y_offsets
    assert len(offsets) == 10
    assert offsets[0] == 0.0
    for i in range(1, 10):
        assert offsets[i] > offsets[i - 1]
    renderer.close_document()


def test_visible_page_range(qapp, multipage_pdf):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    renderer.open_document(multipage_pdf)
    vp_rect = QRectF(0, 0, 800, 600)
    visible = renderer.visible_page_range(vp_rect)
    assert 0 in visible
    renderer.close_document()


def test_close_document_clears_state(qapp, sample_pdf):
    engine = PDFEngine()
    renderer = PageRenderer(main_engine=engine)
    renderer.open_document(sample_pdf)
    renderer.close_document()
    assert renderer.page_count == 0
    assert renderer.total_height == 0
