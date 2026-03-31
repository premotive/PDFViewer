import fitz
from pathlib import Path
from pdf_engine import PDFEngine


def test_open_pdf(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    assert engine.page_count == 1
    assert engine.is_open
    engine.close()
    assert not engine.is_open


def test_open_returns_page_rects(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    rects = engine.page_rects
    assert len(rects) == 1
    assert rects[0].width == 612
    assert rects[0].height == 792
    engine.close()


def test_open_multipage(multipage_pdf):
    engine = PDFEngine()
    engine.open(multipage_pdf)
    assert engine.page_count == 10
    rects = engine.page_rects
    assert len(rects) == 10
    engine.close()


def test_extract_text_dict(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    text_dict = engine.extract_text_dict(0)
    all_text = ""
    for block in text_dict["blocks"]:
        if block["type"] == 0:
            for line in block["lines"]:
                for span in line["spans"]:
                    all_text += span["text"]
    assert "Hello World" in all_text
    assert "Second line" in all_text
    engine.close()


def test_extract_page_text(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    text = engine.extract_page_text(0)
    assert "Hello World" in text
    assert "Second line" in text
    engine.close()


def test_render_pixmap(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    pixmap = engine.render_pixmap(0, dpi=72)
    assert pixmap.width == 612
    assert pixmap.height == 792
    engine.close()


def test_render_pixmap_higher_dpi(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    pixmap = engine.render_pixmap(0, dpi=150)
    assert pixmap.width == 1275
    assert pixmap.height == 1650
    engine.close()


def test_password_pdf_needs_auth(password_pdf):
    engine = PDFEngine()
    needs_pass = engine.open(password_pdf)
    assert needs_pass is True
    assert engine.page_count == 0
    success = engine.authenticate("testpass")
    assert success is True
    assert engine.page_count == 1
    text = engine.extract_page_text(0)
    assert "Secret content" in text
    engine.close()


def test_password_pdf_wrong_password(password_pdf):
    engine = PDFEngine()
    engine.open(password_pdf)
    success = engine.authenticate("wrongpass")
    assert success is False
    engine.close()


def test_open_nonexistent_raises(tmp_path):
    engine = PDFEngine()
    try:
        engine.open(tmp_path / "nope.pdf")
        assert False, "Should have raised"
    except FileNotFoundError:
        pass


def test_extract_spans_with_metadata(sample_pdf):
    engine = PDFEngine()
    engine.open(sample_pdf)
    spans = engine.extract_spans(0)
    assert len(spans) >= 2
    first = spans[0]
    assert "text" in first
    assert "bbox" in first
    assert "font" in first
    assert "size" in first
    assert "color" in first
    assert first["text"] == "Hello World"
    engine.close()


def test_font_matching_base14():
    from pdf_engine import match_font
    result = match_font("Helvetica", flags=0)
    assert result == "helv"
    result = match_font("Helvetica-Bold", flags=0)
    assert result == "hebo"
    result = match_font("Times-Roman", flags=0)
    assert result == "tiro"


def test_font_matching_fallback():
    from pdf_engine import match_font
    result = match_font("SomeWeirdFont", flags=0)
    assert result is not None
    assert isinstance(result, str)
