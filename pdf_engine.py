"""PyMuPDF wrapper: open, extract, render, save."""

import fitz
from pathlib import Path

_BASE14_MAP = {
    "helvetica": "helv",
    "helvetica-bold": "hebo",
    "helvetica-oblique": "heit",
    "helvetica-boldoblique": "hebi",
    "times-roman": "tiro",
    "times-bold": "tibo",
    "times-italic": "tiit",
    "times-bolditalic": "tibi",
    "courier": "cour",
    "courier-bold": "cobo",
    "courier-oblique": "coit",
    "courier-boldoblique": "cobi",
    "symbol": "symb",
    "zapfdingbats": "zadb",
}

_BASE14_SHORT = set(_BASE14_MAP.values())

_SERIF_HINTS = ["serif", "times", "garamond", "georgia", "cambria", "palatino", "book"]
_MONO_HINTS = ["mono", "courier", "consola", "menlo", "fira code", "source code"]


def match_font(font_name: str, flags: int) -> str:
    """Match a PDF font name to the best available fitz fontname for insert_textbox.

    flags: Bit 0=superscript, 1=italic, 2=serif, 3=monospace, 4=bold.
    """
    name_lower = font_name.lower().replace(" ", "").replace("-", "")

    # Exact match first, then longest-key substring match to avoid "helvetica"
    # matching before "helveticabold" when the input is "Helvetica-Bold".
    best_match: str | None = None
    best_len = -1
    for base_name, short in _BASE14_MAP.items():
        stripped = base_name.replace("-", "")
        if stripped == name_lower or name_lower == short:
            return short
        if stripped in name_lower and len(stripped) > best_len:
            best_match = short
            best_len = len(stripped)
    if best_match is not None:
        return best_match

    if name_lower in _BASE14_SHORT:
        return name_lower

    is_bold = bool(flags & (1 << 4)) or "bold" in name_lower
    is_italic = bool(flags & (1 << 1)) or "italic" in name_lower or "oblique" in name_lower

    if any(h in name_lower for h in _MONO_HINTS) or bool(flags & (1 << 3)):
        if is_bold and is_italic:
            return "cobi"
        elif is_bold:
            return "cobo"
        elif is_italic:
            return "coit"
        return "cour"
    elif any(h in name_lower for h in _SERIF_HINTS) or bool(flags & (1 << 2)):
        if is_bold and is_italic:
            return "tibi"
        elif is_bold:
            return "tibo"
        elif is_italic:
            return "tiit"
        return "tiro"
    else:
        if is_bold and is_italic:
            return "hebi"
        elif is_bold:
            return "hebo"
        elif is_italic:
            return "heit"
        return "helv"


class PDFEngine:
    """Wraps a single fitz.Document for PDF operations."""

    def __init__(self):
        self._doc: fitz.Document | None = None
        self._path: Path | None = None

    @property
    def is_open(self) -> bool:
        return self._doc is not None

    @property
    def page_count(self) -> int:
        if self._doc is None or self._doc.is_encrypted:
            return 0
        return len(self._doc)

    @property
    def page_rects(self) -> list[fitz.Rect]:
        if self._doc is None:
            return []
        return [self._doc[i].rect for i in range(len(self._doc))]

    def open(self, path: Path) -> bool:
        """Open a PDF. Returns True if password is needed."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        self._doc = fitz.open(str(path))
        self._path = path
        return bool(self._doc.needs_pass)

    def authenticate(self, password: str) -> bool:
        if self._doc is None:
            return False
        return self._doc.authenticate(password) > 0

    def close(self):
        if self._doc is not None:
            self._doc.close()
            self._doc = None
            self._path = None

    def render_pixmap(self, page_num: int, dpi: int = 150) -> fitz.Pixmap:
        page = self._doc[page_num]
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        return page.get_pixmap(matrix=mat)

    def extract_text_dict(self, page_num: int) -> dict:
        page = self._doc[page_num]
        return page.get_text("dict")

    def extract_page_text(self, page_num: int) -> str:
        page = self._doc[page_num]
        return page.get_text("text")

    def extract_spans(self, page_num: int) -> list[dict]:
        """Extract flat list of text spans with metadata."""
        text_dict = self.extract_text_dict(page_num)
        spans = []
        for b_idx, block in enumerate(text_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for l_idx, line in enumerate(block.get("lines", [])):
                for s_idx, span in enumerate(line.get("spans", [])):
                    spans.append({
                        "text": span["text"],
                        "bbox": span["bbox"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                        "flags": span["flags"],
                        "block_num": b_idx,
                        "line_num": l_idx,
                        "span_num": s_idx,
                    })
        return spans

    def save_edits(self, edits: dict, output_path: Path) -> list[str]:
        """Save edited spans using white-out + insert. Returns warning messages."""
        warnings = []
        font_warned = False

        pages_to_edit: dict[int, list] = {}
        for (page_num, _span_id), edit_info in edits.items():
            pages_to_edit.setdefault(page_num, []).append(edit_info)

        for page_num, page_edits in pages_to_edit.items():
            page = self._doc[page_num]
            for edit in page_edits:
                rect = fitz.Rect(edit["original_rect"])
                new_text = edit["new_text"]
                fontname = match_font(edit["font"], edit["flags"])
                fontsize = edit["size"]
                int_color = edit["color"]
                r = ((int_color >> 16) & 0xFF) / 255.0
                g = ((int_color >> 8) & 0xFF) / 255.0
                b = (int_color & 0xFF) / 255.0
                color = (r, g, b)

                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                overflow = page.insert_textbox(
                    rect, new_text, fontname=fontname, fontsize=fontsize, color=color,
                )
                if overflow < 0:
                    min_size = fontsize * 0.7
                    current_size = fontsize - 0.5
                    while current_size >= min_size and overflow < 0:
                        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                        overflow = page.insert_textbox(
                            rect, new_text, fontname=fontname, fontsize=current_size, color=color,
                        )
                        current_size -= 0.5
                    if overflow < 0:
                        warnings.append(
                            f"Text overflow on page {page_num + 1}: "
                            f"'{new_text[:30]}...' didn't fit in original bounds"
                        )

                if fontname != edit["font"].lower() and not font_warned:
                    warnings.append(
                        "Some fonts were substituted — "
                        "saved text may look slightly different from the original."
                    )
                    font_warned = True

        self._doc.save(str(output_path))
        return warnings
