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
