"""Unified toolbar with hamburger menu, file actions, theme, and zoom controls."""

from PySide6.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QLabel, QColorDialog, QMenu, QToolButton,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal


class ToolBar(QToolBar):
    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    theme_selected = Signal(str)
    bg_color_selected = Signal(str)
    font_color_selected = Signal(str)
    zoom_selected = Signal(str)
    mode_toggle_requested = Signal()
    find_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self._build_hamburger()
        self.addSeparator()
        self._build_file_actions()
        self.addSeparator()
        self._build_theme_controls()
        self.addSeparator()
        self._build_zoom_controls()

    def _build_hamburger(self):
        self.hamburger_btn = QToolButton()
        self.hamburger_btn.setText("☰")
        self.hamburger_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.hamburger_btn.setStyleSheet("font-size: 16px; padding: 2px 6px;")

        menu = QMenu(self.hamburger_btn)

        # File section
        menu.addAction(self._make_action("Open", "Ctrl+O", self.open_requested.emit, menu))
        self.save_menu_action = self._make_action("Save", "Ctrl+S", self.save_requested.emit, menu)
        self.save_menu_action.setEnabled(False)
        menu.addAction(self.save_menu_action)
        menu.addAction(self._make_action("Save As", "Ctrl+Shift+S", self.save_as_requested.emit, menu))
        menu.addSeparator()

        # Edit section
        self.undo_action = QAction("Undo", menu)
        self.undo_action.setShortcut("Ctrl+Z")
        menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", menu)
        self.redo_action.setShortcut("Ctrl+Y")
        menu.addAction(self.redo_action)
        menu.addSeparator()

        # View section
        menu.addAction(self._make_action("Find", "Ctrl+F", self.find_requested.emit, menu))
        self.mode_action = self._make_action(
            "Toggle Reading/Faithful Mode", "F5", self.mode_toggle_requested.emit, menu
        )
        menu.addAction(self.mode_action)

        self.hamburger_btn.setMenu(menu)
        self.addWidget(self.hamburger_btn)

    def _make_action(self, text: str, shortcut: str, slot, parent) -> QAction:
        action = QAction(text, parent)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    def _build_file_actions(self):
        self.open_action = QAction("Open", self)
        self.open_action.triggered.connect(self.open_requested.emit)
        self.addAction(self.open_action)
        self.save_action = QAction("Save", self)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_requested.emit)
        self.addAction(self.save_action)
        self.save_as_action = QAction("Save As", self)
        self.save_as_action.triggered.connect(self.save_as_requested.emit)
        self.addAction(self.save_as_action)

    def _build_theme_controls(self):
        self.addWidget(QLabel(" Theme: "))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Sepia", "Dark", "AMOLED Dark", "Custom"])
        self.theme_combo.setCurrentText("Dark")
        self.theme_combo.currentTextChanged.connect(
            lambda t: self.theme_selected.emit(t.lower().replace(" ", "_")))
        self.addWidget(self.theme_combo)
        self.bg_color_btn = QPushButton("BG")
        self.bg_color_btn.setToolTip("Background Color")
        self.bg_color_btn.setFixedWidth(40)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        self.addWidget(self.bg_color_btn)
        self.font_color_btn = QPushButton("Font")
        self.font_color_btn.setToolTip("Font Color")
        self.font_color_btn.setFixedWidth(45)
        self.font_color_btn.clicked.connect(self._pick_font_color)
        self.addWidget(self.font_color_btn)

    def _build_zoom_controls(self):
        self.addWidget(QLabel(" Zoom: "))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "300%", "Fit Width", "Fit Page"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(
            lambda t: self.zoom_selected.emit(t.replace("%", "").strip().lower().replace(" ", "_")))
        self.addWidget(self.zoom_combo)

    def set_dirty(self, dirty: bool):
        self.save_action.setEnabled(dirty)
        self.save_menu_action.setEnabled(dirty)

    def connect_undo_stack(self, undo_stack):
        """Connect undo/redo actions to an undo stack."""
        try:
            self.undo_action.triggered.disconnect()
        except RuntimeError:
            pass
        try:
            self.redo_action.triggered.disconnect()
        except RuntimeError:
            pass
        self.undo_action.triggered.connect(undo_stack.undo)
        self.redo_action.triggered.connect(undo_stack.redo)

    def _pick_bg_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color_selected.emit(color.name())

    def _pick_font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.font_color_selected.emit(color.name())
