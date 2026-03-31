from PySide6.QtGui import QColor
from theme_engine import ThemeEngine, Theme, THEMES


def test_preset_themes_exist():
    assert "light" in THEMES
    assert "sepia" in THEMES
    assert "dark" in THEMES
    assert "amoled_dark" in THEMES
    assert "custom" in THEMES


def test_theme_has_colors():
    dark = THEMES["dark"]
    assert dark.bg_color == "#1E1E1E"
    assert dark.font_color == "#D4D4D4"


def test_theme_engine_default():
    engine = ThemeEngine()
    assert engine.current_theme_name == "dark"
    assert engine.display_mode == "reading"


def test_set_theme():
    engine = ThemeEngine()
    engine.set_theme("sepia")
    assert engine.current_theme_name == "sepia"
    assert engine.bg_color == QColor("#F4ECD8")
    assert engine.font_color == QColor("#5B4636")


def test_set_custom_colors():
    engine = ThemeEngine()
    engine.set_custom_colors("#112233", "#AABBCC")
    assert engine.current_theme_name == "custom"
    assert engine.bg_color == QColor("#112233")
    assert engine.font_color == QColor("#AABBCC")


def test_display_mode_toggle():
    engine = ThemeEngine()
    engine.set_display_mode("faithful")
    assert engine.display_mode == "faithful"
    engine.set_display_mode("reading")
    assert engine.display_mode == "reading"


def test_toggle_mode():
    engine = ThemeEngine()
    engine.set_display_mode("faithful")
    engine.toggle_display_mode()
    assert engine.display_mode == "reading"
    engine.toggle_display_mode()
    assert engine.display_mode == "faithful"


def test_faithful_mode_hides_tint():
    engine = ThemeEngine()
    engine.set_display_mode("faithful")
    assert engine.show_tint is False
    assert engine.show_text_overlays is False


def test_reading_mode_shows_tint():
    engine = ThemeEngine()
    engine.set_display_mode("reading")
    assert engine.show_tint is True
    assert engine.show_text_overlays is True
