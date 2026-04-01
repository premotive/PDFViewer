# Block-Level Text Editing with Whitespace Extension

## Problem

The PDF viewer edits text one span at a time (a span is a single formatting run, often a fragment of a line). Editing a paragraph requires dozens of individual double-clicks. Users need to edit whole paragraphs — including adding substantial text or full rewrites.

## Solution

Double-clicking any text span opens an editor for the entire **block** (paragraph) that contains it. The editor wraps text at the block's width and grows vertically as needed. On save, if text exceeds the original block rect, it extends into available whitespace below. A dashed border shows the maximum available editing area so the user knows their limits.

## Architecture

### Block Data Extraction

Add `extract_blocks()` to `PDFEngine` that returns block-level data:

```python
{
    "block_num": int,
    "bbox": (x0, y0, x1, y1),
    "text": str,  # all lines joined with \n
    "spans": [span_data, ...],  # all child spans for undo
    "dominant_font": str,
    "dominant_size": float,
    "dominant_color": int,
    "dominant_flags": int,
    "align": int,  # 0=left, 1=center, 2=right, 3=justified
}
```

**Dominant font/size/flags** = most common values across the block's spans, weighted by character count.

**Alignment detection**: Infer from span positions within the block bbox:
- If all lines start at (or near) the left edge of the block: left-aligned
- If line centers cluster around the block center: centered
- If all lines end at (or near) the right edge: right-aligned
- If lines both start at left AND end at right (with one short final line): justified
- Default to left-aligned if ambiguous

### Whitespace Detection

Add `compute_max_block_rect()` to `PDFEngine`:

1. Get all blocks on the page (text AND image blocks, type 0 and 1)
2. For each other block, check **horizontal overlap** with the target block
3. Find the nearest overlapping block below
4. Max y1 = `min(nearest_block_top - 4pt, page_bottom - margin)`
5. Return the extended rect (no artificial cap — the actual next obstacle is the limit)

Multi-column handling: only blocks with horizontal overlap constrain extension. A block in column 2 does not limit column 1.

### Editing Flow

In `main.py`:

1. **Double-click** a span -> `_handle_double_click` identifies the span's `block_num`
2. Call `PDFEngine.extract_blocks()` to get block data for that block_num
3. If block text is empty/whitespace-only, skip (don't enter edit mode)
4. Set `_is_editing = True` on all `SpanOverlay`s in the block (suppresses hover highlights)
5. Hide all `SpanOverlay`s belonging to that block
6. Compute the max available rect via `compute_max_block_rect()`
7. Draw a **dashed border** (`QGraphicsRectItem` with `Qt.DashLine` pen) around the max available area so the user can see their space limit
8. Create `QGraphicsTextItem`:
   - Position at block bbox top-left (scaled + y_offset)
   - `setTextWidth(block_width * scale)`
   - Pre-filled with block text (lines joined by `\n`)
   - `TextEditorInteraction` flag set
   - Font color matched to theme (reading mode) or black (faithful mode)
9. **Cursor placement**: Position the text cursor closest to the double-click location within the text, not at position 0
10. User edits freely; text wraps at block width and grows vertically
11. Status bar shows: `"Editing paragraph — Escape to discard, click away to save"`

**Exit paths:**
- **Escape**: discard all changes, restore original text (no undo entry created)
- **Focus-out / click away**: save changes (creates undo entry if text changed)
- **Tab**: save changes and advance to the next block in reading order

### Save Mechanics

In `PDFEngine.save_edits()`, handle block edits alongside span edits:

1. **White-out the original block bbox only** (not the extension — that area is already empty)
2. **Try original block rect**: `insert_textbox` with block rect and detected `align` value
3. **If overflow, try extended rect**: use `compute_max_block_rect()` result, same alignment
4. **If still overflow, shrink font**: reduce by 0.5pt down to 70% of original
5. **If still overflow**: warn via return value, save what fits

PyMuPDF `insert_textbox` align values: 0=left, 1=center, 2=right, 3=justified.

### Edit Tracking & Undo

New `BlockEditCommand(QUndoCommand)` in `editor.py`:

- Stores: page_num, block_num, block_bbox, extended_bbox, all original span data (text + metadata per span), new_text, dominant font info, alignment
- `redo()`: records block edit in tracker, updates overlay display (replaces all block spans with single combined text)
- `undo()`: restores all original span texts and overlay states individually

`EditTracker` gets a parallel dict: `_block_edits: dict[tuple[int, int], dict]` keyed by `(page_num, block_num)`.

When a block edit starts, any existing per-span edits for spans in that block are cleared (block edit supersedes).

`save_edits()` processes block edits after span edits. If a span edit and block edit target the same block, the block edit wins.

### OverlayManager Changes

Add `get_block_overlays(page_num, block_num) -> list[SpanOverlay]` to filter overlays by block number. Used to:
- Hide/show all spans in a block during editing
- Set/clear `_is_editing` flag on all block spans

### Visual Edit Boundary

When editing begins, draw a `QGraphicsRectItem` covering the max available rect (original block + whitespace extension):
- Pen: dashed line, subtle color (semi-transparent theme font color)
- Brush: no fill (transparent)
- zValue: above overlays but below the edit text item
- Removed when editing ends

This gives the user a clear visual of how much room they have.

## Edge Cases

| Case | Handling |
|---|---|
| Mixed formatting in block | Use dominant font/size; acceptable tradeoff for reflow editing |
| Single-span block | Works identically, just one span hidden |
| Empty/whitespace block | Skip, don't enter edit mode |
| Unloaded page | Only allow editing on pages with loaded overlays |
| Multi-column PDF | Whitespace detection checks horizontal overlap only |
| Image blocks as obstacles | Included in whitespace calculation (block type 1) |
| Existing span edits in same block | Cleared when block edit starts |
| Last block on page | Extends to page bottom minus margin |
| Tab navigation | Advances to next block (by y-position, then x-position) |
| Escape during edit | Discards changes, restores original text, no undo entry |
| Re-editing a previously edited block | Works — overlay texts were updated by prior edit, undo chain handles restoration to true original |
| User shrinks text | White-out still covers full original block rect; shorter text leaves white space at bottom, which is correct |

## Known Limitations

- **Block detection accuracy**: PyMuPDF sometimes splits one visual paragraph across multiple blocks (common with certain PDF generators). The user would need to edit each detected block separately in these cases.
- **Mixed formatting loss**: A paragraph with bold/italic words loses per-word formatting when re-saved as a single `insert_textbox` call. This is inherent to the reflow approach.

## Files Modified

- `pdf_engine.py` — add `extract_blocks()`, `compute_max_block_rect()`
- `text_overlay.py` — add `OverlayManager.get_block_overlays()`
- `editor.py` — add `BlockEditCommand`, update `EditTracker` for block edits
- `main.py` — rewrite `_handle_double_click`, `_enter_edit_mode`, `_exit_edit_mode`, `_advance_to_next_span` (rename to `_advance_to_next_block`); add boundary indicator drawing; fix Escape = discard semantics
