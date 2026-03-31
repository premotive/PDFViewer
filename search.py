"""Full-text search across PDF pages and search bar widget."""

import re
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox,
)
from PySide6.QtCore import Qt, Signal


class SearchEngine:
    def __init__(self):
        self._pages: dict[int, str] = {}
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def mark_ready(self):
        self._ready = True

    def set_page_text(self, page_num: int, text: str):
        self._pages[page_num] = text

    def clear(self):
        self._pages.clear()
        self._ready = False

    def search(self, query: str, case_sensitive: bool = False) -> list[dict]:
        if not query:
            return []
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)
        results = []
        for page_num in sorted(self._pages.keys()):
            text = self._pages[page_num]
            for match in pattern.finditer(text):
                results.append({"page": page_num, "start": match.start(), "end": match.end()})
        return results

    def search_with_quads(self, query: str, doc, case_sensitive: bool = False) -> list[dict]:
        """Search with quad positions for highlighting. Uses fitz page.search_for()."""
        if not query:
            return []
        results = []
        for page_num in sorted(self._pages.keys()):
            if page_num >= len(doc):
                continue
            page = doc[page_num]
            quads = page.search_for(query)
            for quad in quads:
                results.append({"page": page_num, "quads": [quad], "rect": quad.rect})
        return results


class SearchBar(QWidget):
    search_requested = Signal(str, bool)
    next_requested = Signal()
    prev_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Find in document...")
        self._input.returnPressed.connect(self._on_search)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        self._case_check = QCheckBox("Aa")
        self._case_check.setToolTip("Case sensitive")
        self._case_check.toggled.connect(self._on_search)
        layout.addWidget(self._case_check)

        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(30)
        self._prev_btn.clicked.connect(self.prev_requested.emit)
        layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(30)
        self._next_btn.clicked.connect(self.next_requested.emit)
        layout.addWidget(self._next_btn)

        self._count_label = QLabel("")
        self._count_label.setMinimumWidth(80)
        layout.addWidget(self._count_label)

        self._close_btn = QPushButton("x")
        self._close_btn.setFixedWidth(30)
        self._close_btn.clicked.connect(self._close)
        layout.addWidget(self._close_btn)

    def show_bar(self):
        self.setVisible(True)
        self._input.setFocus()
        self._input.selectAll()

    def set_indexing(self):
        self._count_label.setText("Indexing...")

    def update_count(self, current: int, total: int):
        if total == 0:
            self._count_label.setText("No results")
        else:
            self._count_label.setText(f"{current + 1} of {total}")

    def _on_search(self):
        self.search_requested.emit(self._input.text(), self._case_check.isChecked())

    def _on_text_changed(self):
        self._on_search()

    def _close(self):
        self.setVisible(False)
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(event)
