# Block-Level Text Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-span text editing with block (paragraph) level editing that supports adding substantial text by extending into whitespace below.

**Architecture:** Double-click opens an editor for the entire block containing the clicked span. The editor uses the block's width for wrapping and can grow vertically. On save, text is inserted into the block rect (or an extended rect if needed). A dashed boundary shows available space.

**Tech Stack:** PySide6, PyMuPDF (fitz), pytest

**Test runner:** `./venv/Scripts/python -m pytest tests/ -x -v` from `C:\Users\Noah\Documents\Tool_Projects\PDFViewer`

**Spec:** `docs/superpowers/specs/2026-03-30-block-editing-design.md`

---

### Task 1: Test Fixture — Paragraph PDF

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add `paragraph_pdf` fixture**

Add after the `password_pdf` fixture (line 118):

```python
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
```

- [ ] **Step 2: Run tests to verify fixtures don't break anything**

Run: `./venv/Scripts/python -m pytest tests/ -x -v`
Expected: All 77 existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add paragraph and two-column PDF fixtures for block editing"
```

---

### Task 2: Block Data Extraction — `extract_blocks()` and Alignment Detection

**Files:**
- Modify: `pdf_engine.py:138-158`
- Test: `tests/test_pdf_engine.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pdf_engine.py`:

```python
def test_extract_blocks_returns_block_data(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    assert len(blocks) >= 2
    first = blocks[0]
    assert "block_num" in first
    assert "bbox" in first
    assert "text" in first
    assert "spans" in first
    assert "dominant_font" in first
    assert "dominant_size" in first
    assert "dominant_color" in first
    assert "dominant_flags" in first
    assert "align" in first
    assert "first paragraph" in first["text"].lower()
    engine.close()


def test_extract_blocks_text_joins_lines(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    # The first block should have multi-line text joined by newlines
    first = blocks[0]
    assert "\n" in first["text"] or len(first["spans"]) >= 1
    engine.close()


def test_extract_blocks_dominant_font(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    first = blocks[0]
    # Both blocks use helv
    assert first["dominant_font"] is not None
    assert first["dominant_size"] > 0
    engine.close()


def test_extract_blocks_spans_have_block_num(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    first = blocks[0]
    for span in first["spans"]:
        assert span["block_num"] == first["block_num"]
    engine.close()


def test_extract_blocks_alignment_default_left(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    # insert_textbox defaults to left alignment
    assert blocks[0]["align"] == 0
    engine.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py::test_extract_blocks_returns_block_data -v`
Expected: FAIL with `AttributeError: 'PDFEngine' object has no attribute 'extract_blocks'`

- [ ] **Step 3: Implement `_detect_alignment` and `extract_blocks`**

Add this helper function before the `PDFEngine` class in `pdf_engine.py` (after line 79):

```python
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

    # Justified: most lines touch both edges
    if left_count >= total - 1 and right_count >= total - 1 and total > 1:
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
```

Add this method to the `PDFEngine` class, after `extract_spans` (after line 158):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py -k "extract_blocks" -v`
Expected: All 5 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add pdf_engine.py tests/test_pdf_engine.py
git commit -m "feat: add extract_blocks with dominant formatting and alignment detection"
```

---

### Task 3: Whitespace Detection — `compute_max_block_rect()`

**Files:**
- Modify: `pdf_engine.py` (add method to `PDFEngine` class after `extract_blocks`)
- Test: `tests/test_pdf_engine.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pdf_engine.py`:

```python
def test_compute_max_block_rect_basic(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    block_0_num = blocks[0]["block_num"]
    result = engine.compute_max_block_rect(0, block_0_num)
    # Should extend from block 0's top to just above block 1
    assert result is not None
    x0, y0, x1, max_y1 = result
    # max_y1 should be less than block 1's top (300) minus margin
    assert max_y1 < 300
    # max_y1 should be greater than block 0's bottom (~160)
    assert max_y1 > blocks[0]["bbox"][3]
    engine.close()


def test_compute_max_block_rect_last_block(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    last_block_num = blocks[-1]["block_num"]
    result = engine.compute_max_block_rect(0, last_block_num)
    assert result is not None
    _, _, _, max_y1 = result
    # Last block should extend toward page bottom (792 minus margin)
    assert max_y1 > 700
    assert max_y1 <= 792
    engine.close()


def test_compute_max_block_rect_column_independence(two_column_pdf):
    engine = PDFEngine()
    engine.open(two_column_pdf)
    blocks = engine.extract_blocks(0)
    # Find the left column first block
    left_block = None
    for b in blocks:
        if b["bbox"][0] < 200:
            left_block = b
            break
    assert left_block is not None

    result = engine.compute_max_block_rect(0, left_block["block_num"])
    assert result is not None
    _, _, _, max_y1 = result

    # Right column block (at y=72) should NOT constrain the left column.
    # Left column should extend down to left_column_block_2 at y=400 (minus margin).
    # The right column block has no horizontal overlap, so it's ignored.
    assert max_y1 > 300  # can reach well past the right column block's y
    engine.close()


def test_compute_max_block_rect_preserves_x(paragraph_pdf):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    block = blocks[0]
    result = engine.compute_max_block_rect(0, block["block_num"])
    # x0, x1 should match the original block
    assert result[0] == block["bbox"][0]
    assert result[2] == block["bbox"][2]
    engine.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py::test_compute_max_block_rect_basic -v`
Expected: FAIL with `AttributeError: 'PDFEngine' object has no attribute 'compute_max_block_rect'`

- [ ] **Step 3: Implement `compute_max_block_rect`**

Add this method to `PDFEngine`, after `extract_blocks`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py -k "compute_max_block_rect" -v`
Expected: All 4 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add pdf_engine.py tests/test_pdf_engine.py
git commit -m "feat: add compute_max_block_rect for whitespace detection"
```

---

### Task 4: OverlayManager — `get_block_overlays()`

**Files:**
- Modify: `text_overlay.py:107-141` (OverlayManager class)
- Test: `tests/test_text_overlay.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_text_overlay.py`:

```python
def test_get_block_overlays(qapp):
    scene = QGraphicsScene()
    manager = OverlayManager(scene)
    spans = [
        {"text": "Block0 Line1", "bbox": (72, 60, 200, 80), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 0, "span_num": 0},
        {"text": "Block0 Line2", "bbox": (72, 85, 200, 105), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 0, "line_num": 1, "span_num": 0},
        {"text": "Block1 Line1", "bbox": (72, 200, 200, 220), "font": "Helvetica",
         "size": 12.0, "color": 0, "flags": 0, "block_num": 1, "line_num": 0, "span_num": 0},
    ]
    manager.create_overlays(spans, scale=1.0, page_num=0, y_offset=0.0)
    block_0 = manager.get_block_overlays(0, 0)
    assert len(block_0) == 2
    assert all(ov.span_data["block_num"] == 0 for ov in block_0)
    block_1 = manager.get_block_overlays(0, 1)
    assert len(block_1) == 1
    empty = manager.get_block_overlays(0, 99)
    assert len(empty) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_text_overlay.py::test_get_block_overlays -v`
Expected: FAIL with `AttributeError: 'OverlayManager' object has no attribute 'get_block_overlays'`

- [ ] **Step 3: Implement `get_block_overlays`**

Add this method to `OverlayManager` in `text_overlay.py`, after `get_overlays` (after line 117):

```python
    def get_block_overlays(self, page_num: int, block_num: int) -> list[SpanOverlay]:
        """Return all overlays on a page that belong to the given block number."""
        return [
            ov for ov in self._overlays.get(page_num, [])
            if ov.span_data["block_num"] == block_num
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_text_overlay.py::test_get_block_overlays -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add text_overlay.py tests/test_text_overlay.py
git commit -m "feat: add OverlayManager.get_block_overlays for block-level filtering"
```

---

### Task 5: Edit Tracking — Block Edit Support and `BlockEditCommand`

**Files:**
- Modify: `editor.py`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_editor.py`:

```python
def test_record_block_edit(qapp):
    tracker = EditTracker()
    tracker.record_block_edit(
        page_num=0, block_num=1, original_text="Hello world",
        new_text="Hello new world", block_bbox=(72, 60, 300, 160),
        extended_bbox=(72, 60, 300, 296), font="Helvetica", size=12.0,
        color=0, flags=0, align=0,
    )
    assert tracker.is_dirty
    edits = tracker.dirty_block_edits
    assert (0, 1) in edits
    assert edits[(0, 1)]["new_text"] == "Hello new world"


def test_block_edit_revert_removes(qapp):
    tracker = EditTracker()
    tracker.record_block_edit(
        page_num=0, block_num=1, original_text="Hello", new_text="Changed",
        block_bbox=(72, 60, 300, 160), extended_bbox=(72, 60, 300, 296),
        font="Helvetica", size=12.0, color=0, flags=0, align=0,
    )
    tracker.record_block_edit(
        page_num=0, block_num=1, original_text="Hello", new_text="Hello",
        block_bbox=(72, 60, 300, 160), extended_bbox=(72, 60, 300, 296),
        font="Helvetica", size=12.0, color=0, flags=0, align=0,
    )
    assert not tracker.is_dirty
    assert (0, 1) not in tracker.dirty_block_edits


def test_block_edit_supersedes_span_edits(qapp):
    tracker = EditTracker()
    # Add a span edit for block 1
    span_id = (0, (1, 0, 0))
    tracker.record_edit(
        span_id=span_id, original_text="Hello", new_text="Hi",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0,
    )
    assert span_id in tracker.dirty_edits
    # Now add a block edit for block 1 on page 0
    tracker.record_block_edit(
        page_num=0, block_num=1, original_text="Hello world",
        new_text="Changed block", block_bbox=(72, 60, 300, 160),
        extended_bbox=(72, 60, 300, 296), font="Helvetica", size=12.0,
        color=0, flags=0, align=0,
    )
    # Span edit for block 1 should be gone
    assert span_id not in tracker.dirty_edits
    assert (0, 1) in tracker.dirty_block_edits


def test_clear_removes_block_edits(qapp):
    tracker = EditTracker()
    tracker.record_block_edit(
        page_num=0, block_num=0, original_text="A", new_text="B",
        block_bbox=(0, 0, 100, 100), extended_bbox=(0, 0, 100, 200),
        font="helv", size=12.0, color=0, flags=0, align=0,
    )
    tracker.clear()
    assert not tracker.is_dirty
    assert tracker.dirty_block_edits == {}


def test_block_edit_command_undo_redo(qapp):
    from editor import BlockEditCommand
    tracker = EditTracker()
    undo_stack = QUndoStack()
    cmd = BlockEditCommand(
        tracker=tracker, page_num=0, block_num=1,
        old_text="Original", new_text="Changed",
        block_bbox=(72, 60, 300, 160), extended_bbox=(72, 60, 300, 296),
        font="Helvetica", size=12.0, color=0, flags=0, align=0,
    )
    undo_stack.push(cmd)
    assert tracker.is_dirty
    assert tracker.dirty_block_edits[(0, 1)]["new_text"] == "Changed"
    undo_stack.undo()
    assert not tracker.is_dirty
    undo_stack.redo()
    assert tracker.dirty_block_edits[(0, 1)]["new_text"] == "Changed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python -m pytest tests/test_editor.py::test_record_block_edit -v`
Expected: FAIL with `AttributeError: 'EditTracker' object has no attribute 'record_block_edit'`

- [ ] **Step 3: Implement block edit support in `EditTracker` and `BlockEditCommand`**

Replace the full contents of `editor.py` with:

```python
"""Edit tracking and undo/redo support."""

from PySide6.QtGui import QUndoCommand

SpanId = tuple[int, tuple[int, int, int]]
BlockId = tuple[int, int]  # (page_num, block_num)


class EditTracker:
    def __init__(self):
        self._edits: dict[SpanId, dict] = {}
        self._block_edits: dict[BlockId, dict] = {}

    @property
    def is_dirty(self) -> bool:
        return len(self._edits) > 0 or len(self._block_edits) > 0

    @property
    def dirty_edits(self) -> dict[SpanId, dict]:
        return dict(self._edits)

    @property
    def dirty_block_edits(self) -> dict[BlockId, dict]:
        return dict(self._block_edits)

    def record_edit(self, span_id: SpanId, original_text: str, new_text: str,
                    original_rect: tuple, font: str, size: float, color: int, flags: int):
        if new_text == original_text:
            self._edits.pop(span_id, None)
        else:
            self._edits[span_id] = {
                "original_text": original_text, "new_text": new_text,
                "original_rect": original_rect, "font": font, "size": size,
                "color": color, "flags": flags,
            }

    def record_block_edit(self, page_num: int, block_num: int, original_text: str,
                          new_text: str, block_bbox: tuple, extended_bbox: tuple,
                          font: str, size: float, color: int, flags: int, align: int):
        block_id = (page_num, block_num)
        if new_text == original_text:
            self._block_edits.pop(block_id, None)
        else:
            self._block_edits[block_id] = {
                "original_text": original_text, "new_text": new_text,
                "block_bbox": block_bbox, "extended_bbox": extended_bbox,
                "font": font, "size": size, "color": color, "flags": flags,
                "align": align,
            }
        # Block edit supersedes span edits for spans in this block
        to_remove = [
            sid for sid in self._edits
            if sid[0] == page_num and sid[1][0] == block_num
        ]
        for sid in to_remove:
            del self._edits[sid]

    def clear(self):
        self._edits.clear()
        self._block_edits.clear()


class SpanEditCommand(QUndoCommand):
    def __init__(self, tracker: EditTracker, span_id: SpanId, old_text: str, new_text: str,
                 original_rect: tuple, font: str, size: float, color: int, flags: int,
                 text_updater=None):
        super().__init__(f"Edit text on page {span_id[0] + 1}")
        self._tracker = tracker
        self._span_id = span_id
        self._old_text = old_text
        self._new_text = new_text
        self._original_rect = original_rect
        self._font = font
        self._size = size
        self._color = color
        self._flags = flags
        self._text_updater = text_updater

    def redo(self):
        self._tracker.record_edit(
            span_id=self._span_id, original_text=self._old_text, new_text=self._new_text,
            original_rect=self._original_rect, font=self._font, size=self._size,
            color=self._color, flags=self._flags,
        )
        if self._text_updater:
            self._text_updater(self._span_id, self._new_text)

    def undo(self):
        self._tracker.record_edit(
            span_id=self._span_id, original_text=self._old_text, new_text=self._old_text,
            original_rect=self._original_rect, font=self._font, size=self._size,
            color=self._color, flags=self._flags,
        )
        if self._text_updater:
            self._text_updater(self._span_id, self._old_text)


class BlockEditCommand(QUndoCommand):
    def __init__(self, tracker: EditTracker, page_num: int, block_num: int,
                 old_text: str, new_text: str, block_bbox: tuple, extended_bbox: tuple,
                 font: str, size: float, color: int, flags: int, align: int,
                 text_updater=None):
        super().__init__(f"Edit block on page {page_num + 1}")
        self._tracker = tracker
        self._page_num = page_num
        self._block_num = block_num
        self._old_text = old_text
        self._new_text = new_text
        self._block_bbox = block_bbox
        self._extended_bbox = extended_bbox
        self._font = font
        self._size = size
        self._color = color
        self._flags = flags
        self._align = align
        self._text_updater = text_updater

    def redo(self):
        self._tracker.record_block_edit(
            page_num=self._page_num, block_num=self._block_num,
            original_text=self._old_text, new_text=self._new_text,
            block_bbox=self._block_bbox, extended_bbox=self._extended_bbox,
            font=self._font, size=self._size, color=self._color,
            flags=self._flags, align=self._align,
        )
        if self._text_updater:
            self._text_updater(self._page_num, self._block_num, self._new_text)

    def undo(self):
        self._tracker.record_block_edit(
            page_num=self._page_num, block_num=self._block_num,
            original_text=self._old_text, new_text=self._old_text,
            block_bbox=self._block_bbox, extended_bbox=self._extended_bbox,
            font=self._font, size=self._size, color=self._color,
            flags=self._flags, align=self._align,
        )
        if self._text_updater:
            self._text_updater(self._page_num, self._block_num, self._old_text)
```

- [ ] **Step 4: Run all editor tests**

Run: `./venv/Scripts/python -m pytest tests/test_editor.py -v`
Expected: All 11 tests PASS (6 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat: add BlockEditCommand and block edit tracking to EditTracker"
```

---

### Task 6: Save Block Edits — Update `PDFEngine.save_edits()`

**Files:**
- Modify: `pdf_engine.py:160-209` (`save_edits` method)
- Test: `tests/test_pdf_engine.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pdf_engine.py`:

```python
def test_save_block_edits(paragraph_pdf, tmp_path):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    block = blocks[0]
    max_rect = engine.compute_max_block_rect(0, block["block_num"])

    block_edits = {
        (0, block["block_num"]): {
            "original_text": block["text"],
            "new_text": "Completely rewritten paragraph with new content.",
            "block_bbox": block["bbox"],
            "extended_bbox": max_rect,
            "font": block["dominant_font"],
            "size": block["dominant_size"],
            "color": block["dominant_color"],
            "flags": block["dominant_flags"],
            "align": block["align"],
        }
    }
    output = tmp_path / "saved.pdf"
    warnings = engine.save_edits({}, output, block_edits=block_edits)
    assert output.exists()

    # Re-open and verify text was changed
    engine2 = PDFEngine()
    engine2.open(output)
    text = engine2.extract_page_text(0)
    assert "rewritten paragraph" in text.lower()
    engine2.close()
    engine.close()


def test_save_block_edits_with_alignment(paragraph_pdf, tmp_path):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    block = blocks[0]
    max_rect = engine.compute_max_block_rect(0, block["block_num"])

    block_edits = {
        (0, block["block_num"]): {
            "original_text": block["text"],
            "new_text": "Centered text line.",
            "block_bbox": block["bbox"],
            "extended_bbox": max_rect,
            "font": block["dominant_font"],
            "size": block["dominant_size"],
            "color": block["dominant_color"],
            "flags": block["dominant_flags"],
            "align": 1,  # center
        }
    }
    output = tmp_path / "saved_center.pdf"
    warnings = engine.save_edits({}, output, block_edits=block_edits)
    assert output.exists()
    engine.close()


def test_save_block_edit_supersedes_span_edit(paragraph_pdf, tmp_path):
    engine = PDFEngine()
    engine.open(paragraph_pdf)
    blocks = engine.extract_blocks(0)
    block = blocks[0]
    max_rect = engine.compute_max_block_rect(0, block["block_num"])
    first_span = block["spans"][0]

    # Span edit and block edit targeting same block
    span_id = (0, (first_span["block_num"], first_span["line_num"], first_span["span_num"]))
    span_edits = {
        span_id: {
            "original_text": first_span["text"], "new_text": "SPAN EDIT",
            "original_rect": first_span["bbox"], "font": first_span["font"],
            "size": first_span["size"], "color": first_span["color"],
            "flags": first_span["flags"],
        }
    }
    block_edits = {
        (0, block["block_num"]): {
            "original_text": block["text"],
            "new_text": "BLOCK EDIT WINS",
            "block_bbox": block["bbox"],
            "extended_bbox": max_rect,
            "font": block["dominant_font"],
            "size": block["dominant_size"],
            "color": block["dominant_color"],
            "flags": block["dominant_flags"],
            "align": 0,
        }
    }
    output = tmp_path / "saved_conflict.pdf"
    warnings = engine.save_edits(span_edits, output, block_edits=block_edits)

    engine2 = PDFEngine()
    engine2.open(output)
    text = engine2.extract_page_text(0)
    assert "BLOCK EDIT WINS" in text
    assert "SPAN EDIT" not in text
    engine2.close()
    engine.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py::test_save_block_edits -v`
Expected: FAIL with `TypeError` (save_edits doesn't accept block_edits parameter)

- [ ] **Step 3: Rewrite `save_edits` to handle block edits**

Replace the `save_edits` method in `pdf_engine.py` (lines 160-208) with:

```python
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
```

- [ ] **Step 4: Run all pdf_engine tests**

Run: `./venv/Scripts/python -m pytest tests/test_pdf_engine.py -v`
Expected: All tests PASS (existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add pdf_engine.py tests/test_pdf_engine.py
git commit -m "feat: extend save_edits to handle block-level edits with whitespace extension"
```

---

### Task 7: Main Window — Block Edit Mode

**Files:**
- Modify: `main.py`

This task replaces the per-span edit mode with block-level editing. It modifies: `_handle_double_click`, `_enter_edit_mode` (renamed to `_enter_block_edit_mode`), `_exit_edit_mode`, adds `_discard_edit`, replaces `_advance_to_next_span` with `_advance_to_next_block`, updates `_update_span_text` to `_update_block_text`, and updates `_save_to` to pass block edits.

- [ ] **Step 1: Update imports at the top of `main.py`**

Replace lines 7-12:

```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QStatusBar, QGraphicsTextItem,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF
from PySide6.QtGui import QAction, QColor, QKeySequence, QUndoStack
```

With:

```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QStatusBar, QGraphicsTextItem, QGraphicsRectItem,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF, QPointF
from PySide6.QtGui import QAction, QColor, QKeySequence, QUndoStack, QPen, QBrush
```

Replace line 19:

```python
from editor import EditTracker, SpanEditCommand
```

With:

```python
from editor import EditTracker, BlockEditCommand
```

- [ ] **Step 2: Replace `_handle_double_click` (lines 465-472)**

Replace:

```python
    def _handle_double_click(self, scene_pos):
        page_num = self._renderer.current_page()
        overlays = self._renderer.overlay_manager.get_overlays(page_num)
        for overlay in overlays:
            item_pos = overlay.mapFromScene(scene_pos)
            if overlay.boundingRect().contains(item_pos):
                self._enter_edit_mode(overlay)
                return
```

With:

```python
    def _handle_double_click(self, scene_pos):
        page_num = self._renderer.current_page()
        overlay = self._renderer.overlay_manager.find_overlay_at(page_num, scene_pos)
        if overlay is not None:
            block_num = overlay.span_data["block_num"]
            self._enter_block_edit_mode(block_num, page_num, scene_pos)
```

- [ ] **Step 3: Replace `_enter_edit_mode` (lines 474-507)**

Replace the entire `_enter_edit_mode` method with:

```python
    def _enter_block_edit_mode(self, block_num: int, page_num: int, click_scene_pos):
        if self._active_edit is not None:
            self._exit_edit_mode()

        blocks = self._main_engine.extract_blocks(page_num)
        block_data = None
        for b in blocks:
            if b["block_num"] == block_num:
                block_data = b
                break
        if block_data is None or not block_data["text"].strip():
            return

        max_rect = self._main_engine.compute_max_block_rect(page_num, block_num)

        # Set editing flag and hide all block overlays
        block_overlays = self._renderer.overlay_manager.get_block_overlays(page_num, block_num)
        for ov in block_overlays:
            ov._is_editing = True
            ov.hide()

        scale = self._renderer._scale
        y_offset = self._renderer._page_y_offsets[page_num] if page_num < len(self._renderer._page_y_offsets) else 0
        bbox = block_data["bbox"]

        # Draw dashed boundary showing available space
        boundary = None
        if max_rect:
            boundary_rect = QRectF(
                max_rect[0] * scale, max_rect[1] * scale + y_offset,
                (max_rect[2] - max_rect[0]) * scale, (max_rect[3] - max_rect[1]) * scale,
            )
            boundary = QGraphicsRectItem(boundary_rect)
            pen = QPen(QColor(self._theme_engine.font_color))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.0)
            pen.setColor(QColor(
                self._theme_engine.font_color.red(),
                self._theme_engine.font_color.green(),
                self._theme_engine.font_color.blue(),
                100,
            ))
            boundary.setPen(pen)
            boundary.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            boundary.setZValue(2.5)
            self._renderer.scene.addItem(boundary)

        # Create edit text item
        edit_item = QGraphicsTextItem(block_data["text"])
        font = edit_item.font()
        font.setPointSizeF(block_data["dominant_size"] * scale * 0.75)
        dom_flags = block_data["dominant_flags"]
        if dom_flags & (1 << 4):
            font.setBold(True)
        if dom_flags & (1 << 1):
            font.setItalic(True)
        if dom_flags & (1 << 3):
            font.setFamily("Courier")
        edit_item.setFont(font)
        edit_item.setPos(bbox[0] * scale, bbox[1] * scale + y_offset)
        edit_item.setTextWidth((bbox[2] - bbox[0]) * scale)
        edit_item.setZValue(3)
        edit_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        edit_item.setDefaultTextColor(
            self._theme_engine.font_color if self._theme_engine.show_text_overlays else QColor(0, 0, 0)
        )

        self._renderer.scene.addItem(edit_item)
        edit_item.setFocus()

        # Position cursor near click location
        local_pos = edit_item.mapFromScene(click_scene_pos)
        cursor_pos = edit_item.document().documentLayout().hitTest(local_pos, Qt.HitTestAccuracy.FuzzyHit)
        if cursor_pos >= 0:
            cursor = edit_item.textCursor()
            cursor.setPosition(cursor_pos)
            edit_item.setTextCursor(cursor)

        self._active_edit = {
            "type": "block",
            "block_num": block_num,
            "page_num": page_num,
            "block_data": block_data,
            "max_rect": max_rect,
            "edit_item": edit_item,
            "boundary": boundary,
            "overlays": block_overlays,
            "original_text": block_data["text"],
        }

        # Key handling: Escape = discard, Tab = save + next block
        original_key_press = edit_item.keyPressEvent

        def custom_key_press(event):
            if event.key() == Qt.Key.Key_Escape:
                self._discard_edit()
            elif event.key() == Qt.Key.Key_Tab:
                self._exit_edit_mode()
                self._advance_to_next_block(page_num, block_num)
            else:
                original_key_press(event)

        edit_item.keyPressEvent = custom_key_press
        edit_item.focusOutEvent = lambda e: self._exit_edit_mode()
        self._status_bar.showMessage("Editing paragraph \u2014 Escape to discard, click away to save")
```

- [ ] **Step 4: Replace `_exit_edit_mode` (lines 509-542)**

Replace the entire `_exit_edit_mode` method with:

```python
    def _exit_edit_mode(self):
        """Save changes and exit edit mode."""
        if self._active_edit is None:
            return

        edit_data = self._active_edit
        self._active_edit = None

        edit_item = edit_data["edit_item"]
        new_text = edit_item.toPlainText()
        original_text = edit_data["original_text"]

        # Clean up scene items
        self._renderer.scene.removeItem(edit_item)
        if edit_data.get("boundary"):
            self._renderer.scene.removeItem(edit_data["boundary"])

        # Restore overlays
        for ov in edit_data["overlays"]:
            ov._is_editing = False
            ov.show()

        if new_text != original_text:
            block_data = edit_data["block_data"]
            cmd = BlockEditCommand(
                tracker=self._edit_tracker,
                page_num=edit_data["page_num"],
                block_num=edit_data["block_num"],
                old_text=original_text,
                new_text=new_text,
                block_bbox=block_data["bbox"],
                extended_bbox=edit_data["max_rect"],
                font=block_data["dominant_font"],
                size=block_data["dominant_size"],
                color=block_data["dominant_color"],
                flags=block_data["dominant_flags"],
                align=block_data["align"],
                text_updater=self._update_block_text,
            )
            self._undo_stack.push(cmd)
            self._on_dirty_changed(self._edit_tracker.is_dirty)

        self._status_bar.showMessage("Ready")

    def _discard_edit(self):
        """Discard changes and exit edit mode (Escape key)."""
        if self._active_edit is None:
            return

        edit_data = self._active_edit
        self._active_edit = None

        self._renderer.scene.removeItem(edit_data["edit_item"])
        if edit_data.get("boundary"):
            self._renderer.scene.removeItem(edit_data["boundary"])

        for ov in edit_data["overlays"]:
            ov._is_editing = False
            ov.show()

        self._status_bar.showMessage("Edit discarded")
```

- [ ] **Step 5: Replace `_advance_to_next_span` (lines 544-554)**

Replace:

```python
    def _advance_to_next_span(self, current_overlay: SpanOverlay):
        page_num = current_overlay.page_num
        overlays = self._renderer.overlay_manager.get_overlays(page_num)
        sorted_overlays = sorted(
            overlays, key=lambda ov: (ov.span_data["bbox"][1], ov.span_data["bbox"][0])
        )
        for i, ov in enumerate(sorted_overlays):
            if ov.span_id == current_overlay.span_id:
                if i + 1 < len(sorted_overlays):
                    self._enter_edit_mode(sorted_overlays[i + 1])
                return
```

With:

```python
    def _advance_to_next_block(self, page_num: int, current_block_num: int):
        """Tab: save current block edit and open the next block for editing."""
        blocks = self._main_engine.extract_blocks(page_num)
        sorted_blocks = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        for i, b in enumerate(sorted_blocks):
            if b["block_num"] == current_block_num:
                if i + 1 < len(sorted_blocks):
                    next_b = sorted_blocks[i + 1]
                    scale = self._renderer._scale
                    y_offset = self._renderer._page_y_offsets[page_num] if page_num < len(self._renderer._page_y_offsets) else 0
                    click_pos = QPointF(
                        next_b["bbox"][0] * scale,
                        next_b["bbox"][1] * scale + y_offset,
                    )
                    self._enter_block_edit_mode(next_b["block_num"], page_num, click_pos)
                return
```

- [ ] **Step 6: Replace `_update_span_text` (lines 556-562)**

Replace:

```python
    def _update_span_text(self, span_id, text):
        page_num = span_id[0]
        for overlay in self._renderer.overlay_manager.get_overlays(page_num):
            if overlay.span_id == span_id:
                overlay.span_text = text
                break
        self._on_dirty_changed(self._edit_tracker.is_dirty)
```

With:

```python
    def _update_block_text(self, page_num: int, block_num: int, text: str):
        """Update overlay texts for a block after undo/redo."""
        block_overlays = self._renderer.overlay_manager.get_block_overlays(page_num, block_num)
        lines = text.split("\n")
        for i, ov in enumerate(block_overlays):
            if i < len(lines):
                ov.span_text = lines[i]
            else:
                ov.span_text = ""
        self._on_dirty_changed(self._edit_tracker.is_dirty)
```

- [ ] **Step 7: Update `_save_to` to pass block edits (line 259-260)**

In `_save_to`, replace:

```python
            edits = self._edit_tracker.dirty_edits
            if not edits:
                return
```

With:

```python
            edits = self._edit_tracker.dirty_edits
            block_edits = self._edit_tracker.dirty_block_edits
            if not edits and not block_edits:
                return
```

And replace:

```python
            warnings = self._main_engine.save_edits(edits, tmp_path)
```

With:

```python
            warnings = self._main_engine.save_edits(edits, tmp_path, block_edits=block_edits)
```

- [ ] **Step 8: Run the full test suite**

Run: `./venv/Scripts/python -m pytest tests/ -x -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add main.py
git commit -m "feat: replace per-span editing with block-level editing and whitespace extension"
```

---

### Task 8: Full Integration Smoke Test

**Files:**
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_main.py`:

```python
def test_block_edit_mode_available(qapp, paragraph_pdf):
    """Verify the block editing infrastructure is wired up correctly."""
    window = MainWindow()
    window.open_file(paragraph_pdf)
    # Give render worker time to process
    from PySide6.QtCore import QTimer
    import time
    # The engine should be able to extract blocks
    blocks = window._main_engine.extract_blocks(0)
    assert len(blocks) >= 2
    # First block should have text
    assert blocks[0]["text"].strip() != ""
    # Max rect should be computable
    max_rect = window._main_engine.compute_max_block_rect(0, blocks[0]["block_num"])
    assert max_rect is not None
    assert max_rect[3] > blocks[0]["bbox"][3]  # extended past original bottom
    window.close()


def test_edit_tracker_block_dirty_indicator(qapp, paragraph_pdf):
    window = MainWindow()
    window.open_file(paragraph_pdf)
    assert not window._edit_tracker.is_dirty
    blocks = window._main_engine.extract_blocks(0)
    block = blocks[0]
    max_rect = window._main_engine.compute_max_block_rect(0, block["block_num"])
    window._edit_tracker.record_block_edit(
        page_num=0, block_num=block["block_num"],
        original_text=block["text"], new_text="Totally new text",
        block_bbox=block["bbox"], extended_bbox=max_rect,
        font=block["dominant_font"], size=block["dominant_size"],
        color=block["dominant_color"], flags=block["dominant_flags"], align=0,
    )
    assert window._edit_tracker.is_dirty
    window.close()
```

- [ ] **Step 2: Run the full test suite**

Run: `./venv/Scripts/python -m pytest tests/ -x -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_main.py
git commit -m "test: add integration tests for block editing infrastructure"
```
