"""Library sidebar with persistent recently-opened PDF cards."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

@dataclass
class LibraryEntry:
    file_path: str
    filename: str
    page_count: int
    last_opened: str
    thumb_path: str = ""


class LibraryData:
    """Manages a library.json file that tracks recently-opened PDFs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.entries: list[LibraryEntry] = []

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load entries from disk; silently handles missing or corrupt files."""
        if not self._path.exists():
            self.entries = []
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self.entries = [
                LibraryEntry(
                    file_path=item["file_path"],
                    filename=item["filename"],
                    page_count=item["page_count"],
                    last_opened=item["last_opened"],
                    thumb_path=item.get("thumb_path", ""),
                )
                for item in raw
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            self.entries = []

    def save(self) -> None:
        """Persist entries to disk, creating parent directories as needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump([asdict(e) for e in self.entries], fh, indent=2)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_or_update(self, file_path: str, filename: str, page_count: int) -> None:
        """Add a new entry or move an existing one to the front with a fresh timestamp."""
        timestamp = datetime.now(timezone.utc).isoformat()
        # Remove existing entry with the same path (if any)
        existing = self.find(file_path)
        thumb = existing.thumb_path if existing else ""
        self.entries = [e for e in self.entries if e.file_path != file_path]
        # Insert at front (most recent)
        self.entries.insert(
            0,
            LibraryEntry(
                file_path=file_path,
                filename=filename,
                page_count=page_count,
                last_opened=timestamp,
                thumb_path=thumb,
            ),
        )

    def remove(self, file_path: str) -> None:
        """Remove the entry with the given path."""
        self.entries = [e for e in self.entries if e.file_path != file_path]

    def find(self, file_path: str) -> Optional[LibraryEntry]:
        """Return the entry for *file_path*, or None if not present."""
        for entry in self.entries:
            if entry.file_path == file_path:
                return entry
        return None


# ---------------------------------------------------------------------------
# Widget layer
# ---------------------------------------------------------------------------

def _human_age(iso_timestamp: str) -> str:
    """Return a human-readable age string like '2h ago'."""
    try:
        then = datetime.fromisoformat(iso_timestamp)
        # Make both timezone-aware for comparison
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - then
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        return f"{months}mo ago"
    except (ValueError, TypeError):
        return ""


class LibraryCard(QFrame):
    """A card widget representing a single library entry."""

    clicked = Signal(str)           # emits file_path
    remove_requested = Signal(str)  # emits file_path

    def __init__(self, entry: LibraryEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._file_exists = os.path.isfile(entry.file_path)
        self._build_ui()
        self._apply_dim()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedHeight(80)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setText("[ no preview ]")
        self._thumb_label.setStyleSheet("background: #ccc; color: #666; font-size: 10px;")
        layout.addWidget(self._thumb_label)

        if self._entry.thumb_path:
            self.update_thumbnail(self._entry.thumb_path)

        # Filename label
        name_label = QLabel(self._entry.filename)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(name_label)

        # Metadata line: "3 pages · 2h ago"
        age = _human_age(self._entry.last_opened)
        page_word = "page" if self._entry.page_count == 1 else "pages"
        meta_text = f"{self._entry.page_count} {page_word} · {age}" if age else f"{self._entry.page_count} {page_word}"
        meta_label = QLabel(meta_text)
        meta_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(meta_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_thumbnail(self, thumb_path: str) -> None:
        """Update the thumbnail image from *thumb_path*."""
        from PySide6.QtGui import QPixmap

        pixmap = QPixmap(thumb_path)
        if not pixmap.isNull():
            self._thumb_label.setPixmap(
                pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
            )
            self._thumb_label.setStyleSheet("")
        else:
            self._thumb_label.setText("[ no preview ]")

    # ------------------------------------------------------------------
    # Mouse / context menu
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry.file_path)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        remove_action = menu.addAction("Remove from Library")
        chosen = menu.exec(event.globalPos())
        if chosen == open_action:
            self.clicked.emit(self._entry.file_path)
        elif chosen == remove_action:
            self.remove_requested.emit(self._entry.file_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_dim(self) -> None:
        if not self._file_exists:
            self.setStyleSheet("QFrame { opacity: 0.5; color: #aaa; }")


class LibrarySidebar(QWidget):
    """Collapsible sidebar showing recently-opened PDF cards."""

    pdf_open_requested = Signal(str)  # emits file_path

    _CONTENT_WIDTH = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self._cards: list[LibraryCard] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Content panel (left)
        self._content = QWidget()
        self._content.setFixedWidth(self._CONTENT_WIDTH)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(4)

        header = QLabel("Library")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        content_layout.addWidget(header)

        # Scrollable card area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_container)
        content_layout.addWidget(self._scroll)

        root.addWidget(self._content)

        # Toggle button (right, 20px wide)
        self._toggle_btn = QPushButton("◀")
        self._toggle_btn.setFixedWidth(20)
        self._toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        root.addWidget(self._toggle_btn)

    # ------------------------------------------------------------------
    # Collapse / expand
    # ------------------------------------------------------------------

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._content.setVisible(not collapsed)
        self._toggle_btn.setText("▶" if collapsed else "◀")

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    # ------------------------------------------------------------------
    # Card management
    # ------------------------------------------------------------------

    def refresh(self, entries: list[LibraryEntry]) -> None:
        """Rebuild all card widgets from *entries*."""
        # Remove old cards
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for entry in entries:
            card = LibraryCard(entry)
            card.clicked.connect(self.pdf_open_requested.emit)
            card.remove_requested.connect(self._on_remove_requested)
            # Insert before the trailing stretch (last item)
            insert_pos = self._cards_layout.count() - 1
            self._cards_layout.insertWidget(insert_pos, card)
            self._cards.append(card)

    def _on_remove_requested(self, file_path: str) -> None:
        # Remove the card from the UI immediately; caller can persist via signal
        for card in list(self._cards):
            if card._entry.file_path == file_path:
                self._cards_layout.removeWidget(card)
                card.deleteLater()
                self._cards.remove(card)
                break
