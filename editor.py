"""Edit tracking and undo/redo support."""

from PySide6.QtGui import QUndoCommand

SpanId = tuple[int, tuple[int, int, int]]


class EditTracker:
    def __init__(self):
        self._edits: dict[SpanId, dict] = {}

    @property
    def is_dirty(self) -> bool:
        return len(self._edits) > 0

    @property
    def dirty_edits(self) -> dict[SpanId, dict]:
        return dict(self._edits)

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

    def clear(self):
        self._edits.clear()


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
