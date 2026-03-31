"""Theme presets and display mode management."""

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage


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


def transform_image_for_theme(image: QImage, bg_color: QColor, font_color: QColor) -> QImage:
    """Transform a rendered page image to match theme colors.

    Remaps brightness so white→bg_color and black→font_color while
    preserving the original hue ratios of every pixel.  This keeps
    colored boxes, borders, and other non-text elements visible.

    For a light theme (white bg, black font) the result is nearly
    identical to the original image.  Handles both RGB and RGBA images.
    """
    if image.width() == 0 or image.height() == 0:
        return image.copy()

    has_alpha = image.hasAlphaChannel()
    if has_alpha:
        img = image.convertToFormat(QImage.Format.Format_RGBA8888)
        channels = 4
    else:
        img = image.convertToFormat(QImage.Format.Format_RGB888)
        channels = 3

    w, h = img.width(), img.height()
    stride = img.bytesPerLine()
    ptr = img.constBits()
    raw = np.frombuffer(ptr, dtype=np.uint8).reshape((h, stride))
    arr = raw[:, :w * channels].reshape((h, w, channels)).copy()

    rgb = arr[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    lum = np.float32(0.299) * r + np.float32(0.587) * g + np.float32(0.114) * b
    t = lum / np.float32(255.0)

    bg = np.array([bg_color.red(), bg_color.green(), bg_color.blue()], dtype=np.float32)
    fg = np.array([font_color.red(), font_color.green(), font_color.blue()], dtype=np.float32)

    # Base colour: theme gradient from font_color (dark) → bg_color (bright)
    base = fg[np.newaxis, np.newaxis, :] + (bg - fg)[np.newaxis, np.newaxis, :] * t[..., np.newaxis]

    # Chrominance ratio: how far each channel deviates from neutral grey.
    # For very dark pixels the ratio is unreliable, so blend towards the
    # plain base colour as luminance approaches zero.
    safe_lum = np.where(lum > np.float32(1.0), lum, np.float32(1.0))
    ratio = rgb / safe_lum[..., np.newaxis]

    coloured = base * ratio
    blend = np.clip((lum - np.float32(5.0)) / np.float32(35.0),
                    np.float32(0.0), np.float32(1.0))[..., np.newaxis]
    result_rgb = coloured * blend + base * (np.float32(1.0) - blend)
    result_rgb = np.clip(result_rgb, 0, 255).astype(np.uint8)

    if has_alpha:
        result = np.concatenate([result_rgb, arr[..., 3:4]], axis=2)
        fmt = QImage.Format.Format_RGBA8888
    else:
        result = result_rgb
        fmt = QImage.Format.Format_RGB888

    out = QImage(result.tobytes(), w, h, w * channels, fmt)
    return out.copy()


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
    def viewport_bg_color(self) -> QColor:
        """Background color for the area behind pages — always distinct from page color."""
        bg = self.bg_color
        lightness = bg.lightnessF()
        if lightness < 0.08:
            # Near-black (e.g., AMOLED) — can't go darker, use dark gray
            return QColor(25, 25, 25)
        elif lightness < 0.5:
            # Dark/colored theme — go noticeably darker
            return bg.darker(170)
        else:
            # Light theme — use a visible but not harsh gray
            return bg.darker(120)

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
