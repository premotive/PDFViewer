# tests/conftest.py
import sys
import pytest
import fitz
from pathlib import Path
from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def qapp():
    """Single QApplication instance for all tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a simple single-page PDF with known text content."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter size
    page.insert_text(
        point=fitz.Point(72, 72),
        text="Hello World",
        fontsize=12,
        fontname="helv",
        color=(0, 0, 0),
    )
    page.insert_text(
        point=fitz.Point(72, 100),
        text="Second line of text",
        fontsize=10,
        fontname="tiro",
        color=(0, 0, 0),
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def multipage_pdf(tmp_path):
    """Create a 10-page PDF for testing pagination and lazy loading."""
    pdf_path = tmp_path / "multipage.pdf"
    doc = fitz.open()
    for i in range(10):
        page = doc.new_page(width=612, height=792)
        page.insert_text(
            point=fitz.Point(72, 72),
            text=f"Page {i + 1} content",
            fontsize=14,
            fontname="helv",
            color=(0, 0, 0),
        )
        page.insert_text(
            point=fitz.Point(72, 200),
            text=f"More text on page {i + 1} for searching",
            fontsize=10,
            fontname="helv",
            color=(0, 0, 0),
        )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def complex_pdf(tmp_path):
    """Create a PDF with columns, colored text, and varied fonts for layout testing."""
    pdf_path = tmp_path / "complex.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 72
    for line in ["Left column line 1", "Left column line 2", "Left column line 3"]:
        page.insert_text(point=fitz.Point(72, y), text=line, fontsize=10, fontname="helv")
        y += 16
    y = 72
    for line in ["Right column line 1", "Right column line 2", "Right column line 3"]:
        page.insert_text(point=fitz.Point(320, y), text=line, fontsize=10, fontname="helv")
        y += 16
    page.insert_text(
        point=fitz.Point(72, 200),
        text="Bold heading",
        fontsize=16,
        fontname="hebo",
        color=(0.2, 0.2, 0.8),
    )
    page.draw_rect(fitz.Rect(60, 250, 300, 320), color=(0, 0, 0), width=1)
    page.insert_text(
        point=fitz.Point(72, 275),
        text="Text inside a box",
        fontsize=11,
        fontname="helv",
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def password_pdf(tmp_path):
    """Create a password-protected PDF."""
    pdf_path = tmp_path / "protected.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(point=fitz.Point(72, 72), text="Secret content", fontsize=12)
    doc.save(
        str(pdf_path),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="testpass",
        owner_pw="ownerpass",
    )
    doc.close()
    return pdf_path


@pytest.fixture
def paragraph_pdf(tmp_path):
    """PDF with two paragraph blocks and a gap between them for whitespace tests."""
    pdf_path = tmp_path / "paragraph.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Block 0: paragraph near top
    page.insert_textbox(
        fitz.Rect(72, 72, 300, 160),
        "This is the first paragraph with enough text to span multiple lines.",
        fontsize=12, fontname="helv", color=(0, 0, 0),
    )
    # Block 1: paragraph further down (gap from ~160 to 300 = whitespace)
    page.insert_textbox(
        fitz.Rect(72, 300, 300, 380),
        "Second paragraph starts here.",
        fontsize=12, fontname="helv", color=(0, 0, 0),
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def two_column_pdf(tmp_path):
    """PDF with two columns of text that should not constrain each other."""
    pdf_path = tmp_path / "two_column.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Left column block
    page.insert_textbox(
        fitz.Rect(72, 72, 280, 150),
        "Left column paragraph one.",
        fontsize=11, fontname="helv", color=(0, 0, 0),
    )
    # Right column block (no horizontal overlap with left)
    page.insert_textbox(
        fitz.Rect(320, 72, 540, 150),
        "Right column paragraph one.",
        fontsize=11, fontname="helv", color=(0, 0, 0),
    )
    # Left column block 2 (below left column block 1)
    page.insert_textbox(
        fitz.Rect(72, 400, 280, 480),
        "Left column paragraph two.",
        fontsize=11, fontname="helv", color=(0, 0, 0),
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path
