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


def _detect_alignment(block_bbox, lines) -> int:
    """Detect text alignment from line positions within a block.

    Returns: 0=left, 1=center, 2=right, 3=justified.
    """
    if not lines:
        return 0

    b_x0, _, b_x1, _ = block_bbox
    block_width = b_x1 - b_x0
    if block_width <= 0:
        return 0

    tolerance = max(block_width * 0.05, 2.0)
    left_count = 0
    right_count = 0
    total = 0

    for line in lines:
        spans = line.get("spans", [])
        if not spans:
            continue
        total += 1
        line_x0 = min(s["bbox"][0] for s in spans)
        line_x1 = max(s["bbox"][2] for s in spans)

        if abs(line_x0 - b_x0) <= tolerance:
            left_count += 1
        if abs(line_x1 - b_x1) <= tolerance:
            right_count += 1

    if total == 0:
        return 0

    # Justified: most lines touch both edges (exclude the last line which is typically short)
    if left_count >= total * 0.8 and right_count >= (total - 1) * 0.8 and total > 2:
        return 3

    if left_count >= total * 0.8:
        return 0  # left-aligned

    if right_count >= total * 0.8:
        return 2  # right-aligned

    # Centered: line centers cluster around block center
    block_center = (b_x0 + b_x1) / 2
    centered = 0
    for line in lines:
        spans = line.get("spans", [])
        if not spans:
            continue
        line_x0 = min(s["bbox"][0] for s in spans)
        line_x1 = max(s["bbox"][2] for s in spans)
        line_center = (line_x0 + line_x1) / 2
        if abs(line_center - block_center) <= tolerance:
            centered += 1
    if centered >= total * 0.8:
        return 1

    return 0  # default left


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

    def extract_blocks(self, page_num: int) -> list[dict]:
        """Extract block-level data with dominant formatting and alignment."""
        text_dict = self.extract_text_dict(page_num)
        blocks = []
        for b_idx, block in enumerate(text_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue

            lines = block.get("lines", [])
            all_spans = []
            line_texts = []

            for l_idx, line in enumerate(lines):
                line_span_texts = []
                for s_idx, span in enumerate(line.get("spans", [])):
                    span_data = {
                        "text": span["text"],
                        "bbox": span["bbox"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                        "flags": span["flags"],
                        "block_num": b_idx,
                        "line_num": l_idx,
                        "span_num": s_idx,
                    }
                    all_spans.append(span_data)
                    line_span_texts.append(span["text"])
                line_texts.append("".join(line_span_texts))

            text = "\n".join(line_texts)

            # Dominant formatting by character count
            font_counts: dict[str, int] = {}
            size_counts: dict[float, int] = {}
            color_counts: dict[int, int] = {}
            flags_counts: dict[int, int] = {}
            for s in all_spans:
                n = len(s["text"])
                font_counts[s["font"]] = font_counts.get(s["font"], 0) + n
                size_counts[s["size"]] = size_counts.get(s["size"], 0) + n
                color_counts[s["color"]] = color_counts.get(s["color"], 0) + n
                flags_counts[s["flags"]] = flags_counts.get(s["flags"], 0) + n

            blocks.append({
                "block_num": b_idx,
                "bbox": block["bbox"],
                "text": text,
                "spans": all_spans,
                "dominant_font": max(font_counts, key=font_counts.get) if font_counts else "helv",
                "dominant_size": max(size_counts, key=size_counts.get) if size_counts else 12.0,
                "dominant_color": max(color_counts, key=color_counts.get) if color_counts else 0,
                "dominant_flags": max(flags_counts, key=flags_counts.get) if flags_counts else 0,
                "align": _detect_alignment(block["bbox"], lines),
            })

        return blocks

    def compute_max_block_rect(self, page_num: int, block_num: int) -> tuple | None:
        """Compute max rect a block can expand into by detecting whitespace below.

        Returns (x0, y0, x1, max_y1) in PDF coordinates, or None if block not found.
        Only blocks with horizontal overlap constrain the extension (multi-column safe).
        """
        text_dict = self.extract_text_dict(page_num)
        all_blocks = text_dict.get("blocks", [])
        if block_num >= len(all_blocks):
            return None

        target = all_blocks[block_num]
        t_x0, t_y0, t_x1, t_y1 = target["bbox"]

        page_rect = self._doc[page_num].rect
        margin = 4  # points
        max_y1 = page_rect.y1 - margin

        for i, block in enumerate(all_blocks):
            if i == block_num:
                continue
            b_x0, b_y0, b_x1, b_y1 = block["bbox"]

            # Skip blocks with no horizontal overlap
            if b_x1 <= t_x0 or b_x0 >= t_x1:
                continue

            # Only consider blocks below the target
            if b_y0 > t_y1:
                candidate = b_y0 - margin
                if candidate < max_y1:
                    max_y1 = candidate

        return (t_x0, t_y0, t_x1, max_y1)

    def save_edits(self, edits: dict, output_path: Path, *, block_edits: dict | None = None) -> list[str]:
        """Save edited spans and blocks using white-out + insert. Returns warning messages."""
        warnings = []
        font_warned = False

        # Determine which blocks have block-level edits (supersede span edits)
        block_edited = set()
        if block_edits:
            block_edited = set(block_edits.keys())

        # --- Span edits (skip spans whose block has a block edit) ---
        pages_to_edit: dict[int, list] = {}
        for (page_num, span_id_tuple), edit_info in edits.items():
            block_num = span_id_tuple[0]
            if (page_num, block_num) in block_edited:
                continue
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

        # --- Block edits ---
        if block_edits:
            for (page_num, block_num), edit_info in block_edits.items():
                page = self._doc[page_num]
                block_bbox = fitz.Rect(edit_info["block_bbox"])
                extended_bbox = fitz.Rect(edit_info["extended_bbox"])
                new_text = edit_info["new_text"]
                fontname = match_font(edit_info["font"], edit_info["flags"])
                fontsize = edit_info["size"]
                align = edit_info.get("align", 0)

                int_color = edit_info["color"]
                r = ((int_color >> 16) & 0xFF) / 255.0
                g = ((int_color >> 8) & 0xFF) / 255.0
                b = (int_color & 0xFF) / 255.0
                color = (r, g, b)

                # White-out original block area
                page.draw_rect(block_bbox, color=(1, 1, 1), fill=(1, 1, 1))

                # Try fitting in original block rect
                overflow = page.insert_textbox(
                    block_bbox, new_text, fontname=fontname, fontsize=fontsize,
                    color=color, align=align,
                )

                # If overflow and extended rect is larger, try that
                if overflow < 0 and extended_bbox != block_bbox:
                    page.draw_rect(block_bbox, color=(1, 1, 1), fill=(1, 1, 1))
                    overflow = page.insert_textbox(
                        extended_bbox, new_text, fontname=fontname, fontsize=fontsize,
                        color=color, align=align,
                    )

                # If still overflow, shrink font
                if overflow < 0:
                    use_rect = extended_bbox if extended_bbox != block_bbox else block_bbox
                    min_size = fontsize * 0.7
                    current_size = fontsize - 0.5
                    while current_size >= min_size and overflow < 0:
                        page.draw_rect(use_rect, color=(1, 1, 1), fill=(1, 1, 1))
                        overflow = page.insert_textbox(
                            use_rect, new_text, fontname=fontname, fontsize=current_size,
                            color=color, align=align,
                        )
                        current_size -= 0.5
                    if overflow < 0:
                        warnings.append(
                            f"Text overflow on page {page_num + 1}: "
                            f"'{new_text[:30]}...' didn't fit in available space"
                        )

                if fontname != edit_info["font"].lower() and not font_warned:
                    warnings.append(
                        "Some fonts were substituted — "
                        "saved text may look slightly different from the original."
                    )
                    font_warned = True

        self._doc.save(str(output_path))
        return warnings
