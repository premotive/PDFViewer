"""Theme presets and display mode management."""

from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


@dataclass
class Theme:
    bg_color: str
    font_color: str


THEMES: dict[str, Theme] = {
    "light": Theme(bg_color="#FFFFFF", font_color="#000000"),
    "sepia": Theme(bg_color="#F4ECD8", font_color="#5B4636"),
    "dark": Theme(bg_color="#1E1E1E", font_color="#D4D4D4"),
    "amoled_dark": Theme(bg_color="#000000", font_color="#FFFFFF"),
    "custom": Theme(bg_color="#1E1E1E", font_color="#D4D4D4"),
}


class ThemeEngine(QObject):
    theme_changed = Signal()
    mode_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_name = "dark"
        self._custom_bg = "#1E1E1E"
        self._custom_font = "#D4D4D4"
        self._display_mode = "reading"

    @property
    def current_theme_name(self) -> str:
        return self._theme_name

    @property
    def display_mode(self) -> str:
        return self._display_mode

    @property
    def bg_color(self) -> QColor:
        if self._theme_name == "custom":
            return QColor(self._custom_bg)
        return QColor(THEMES[self._theme_name].bg_color)

    @property
    def font_color(self) -> QColor:
        if self._theme_name == "custom":
            return QColor(self._custom_font)
        return QColor(THEMES[self._theme_name].font_color)

    @property
    def show_tint(self) -> bool:
        return self._display_mode == "reading"

    @property
    def show_text_overlays(self) -> bool:
        return self._display_mode == "reading"

    def set_theme(self, name: str):
        if name not in THEMES:
            return
        self._theme_name = name
        self.theme_changed.emit()

    def set_custom_colors(self, bg: str, font: str):
        self._custom_bg = bg
        self._custom_font = font
        self._theme_name = "custom"
        self.theme_changed.emit()

    def set_display_mode(self, mode: str):
        if mode not in ("faithful", "reading"):
            return
        self._display_mode = mode
        self.mode_changed.emit()

    def toggle_display_mode(self):
        if self._display_mode == "faithful":
            self.set_display_mode("reading")
        else:
            self.set_display_mode("faithful")
