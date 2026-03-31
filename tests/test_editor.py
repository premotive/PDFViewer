from PySide6.QtGui import QUndoStack
from editor import EditTracker, SpanEditCommand


def test_edit_tracker_initially_clean(qapp):
    tracker = EditTracker()
    assert not tracker.is_dirty
    assert tracker.dirty_edits == {}


def test_record_edit(qapp):
    tracker = EditTracker()
    span_id = (0, (1, 2, 3))
    tracker.record_edit(
        span_id=span_id, original_text="Hello", new_text="Hi there",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0,
    )
    assert tracker.is_dirty
    assert span_id in tracker.dirty_edits
    assert tracker.dirty_edits[span_id]["new_text"] == "Hi there"


def test_record_edit_updates_existing(qapp):
    tracker = EditTracker()
    span_id = (0, (1, 2, 3))
    tracker.record_edit(span_id=span_id, original_text="Hello", new_text="First edit",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0)
    tracker.record_edit(span_id=span_id, original_text="Hello", new_text="Second edit",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0)
    assert tracker.dirty_edits[span_id]["new_text"] == "Second edit"


def test_revert_to_original_removes_edit(qapp):
    tracker = EditTracker()
    span_id = (0, (1, 2, 3))
    tracker.record_edit(span_id=span_id, original_text="Hello", new_text="Changed",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0)
    tracker.record_edit(span_id=span_id, original_text="Hello", new_text="Hello",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0)
    assert span_id not in tracker.dirty_edits
    assert not tracker.is_dirty


def test_clear_resets_tracker(qapp):
    tracker = EditTracker()
    span_id = (0, (1, 2, 3))
    tracker.record_edit(span_id=span_id, original_text="Hello", new_text="Changed",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0)
    tracker.clear()
    assert not tracker.is_dirty
    assert tracker.dirty_edits == {}


def test_undo_command(qapp):
    tracker = EditTracker()
    undo_stack = QUndoStack()
    span_id = (0, (1, 2, 3))
    cmd = SpanEditCommand(
        tracker=tracker, span_id=span_id, old_text="Hello", new_text="Changed",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0,
    )
    undo_stack.push(cmd)
    assert tracker.is_dirty
    assert tracker.dirty_edits[span_id]["new_text"] == "Changed"
    undo_stack.undo()
    assert not tracker.is_dirty
    undo_stack.redo()
    assert tracker.is_dirty
    assert tracker.dirty_edits[span_id]["new_text"] == "Changed"


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
    span_id = (0, (1, 0, 0))
    tracker.record_edit(
        span_id=span_id, original_text="Hello", new_text="Hi",
        original_rect=(72, 60, 200, 80), font="Helvetica", size=12.0, color=0, flags=0,
    )
    assert span_id in tracker.dirty_edits
    tracker.record_block_edit(
        page_num=0, block_num=1, original_text="Hello world",
        new_text="Changed block", block_bbox=(72, 60, 300, 160),
        extended_bbox=(72, 60, 300, 296), font="Helvetica", size=12.0,
        color=0, flags=0, align=0,
    )
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
