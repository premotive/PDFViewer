"""Main toolbar with file, theme, zoom, and page navigation controls."""

from PySide6.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QSpinBox, QLabel, QColorDialog,
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
    page_jump_requested = Signal(int)
    mode_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self._build_file_actions()
        self.addSeparator()
        self._build_theme_controls()
        self.addSeparator()
        self._build_zoom_controls()
        self.addSeparator()
        self._build_page_navigator()

    def _build_file_actions(self):
        self.open_action = QAction("Open", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_requested.emit)
        self.addAction(self.open_action)
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_requested.emit)
        self.addAction(self.save_action)
        self.save_as_action = QAction("Save As", self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
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
        self.mode_btn = QPushButton("F5: Mode")
        self.mode_btn.setToolTip("Toggle Faithful / Reading mode")
        self.mode_btn.clicked.connect(self.mode_toggle_requested.emit)
        self.addWidget(self.mode_btn)

    def _build_zoom_controls(self):
        self.addWidget(QLabel(" Zoom: "))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%","75%","100%","125%","150%","200%","300%","Fit Width","Fit Page"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(
            lambda t: self.zoom_selected.emit(t.replace("%","").strip().lower().replace(" ","_")))
        self.addWidget(self.zoom_combo)

    def _build_page_navigator(self):
        self.addWidget(QLabel(" Page: "))
        self.page_spinbox = QSpinBox()
        self.page_spinbox.setMinimum(1)
        self.page_spinbox.setMaximum(1)
        self.page_spinbox.valueChanged.connect(self.page_jump_requested.emit)
        self.addWidget(self.page_spinbox)
        self.page_total_label = QLabel("/ 0")
        self.addWidget(self.page_total_label)

    def set_page_count(self, count: int):
        self.page_spinbox.setMaximum(max(count, 1))
        self.page_total_label.setText(f"/ {count}")

    def set_current_page(self, page_num: int):
        self.page_spinbox.blockSignals(True)
        self.page_spinbox.setValue(page_num)
        self.page_spinbox.blockSignals(False)

    def set_dirty(self, dirty: bool):
        self.save_action.setEnabled(dirty)

    def _pick_bg_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color_selected.emit(color.name())

    def _pick_font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.font_color_selected.emit(color.name())
