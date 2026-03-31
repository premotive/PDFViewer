import json
from pathlib import Path
from config import AppConfig, load_config, save_config


def test_default_config_values():
    config = AppConfig()
    assert config.theme == "dark"
    assert config.custom_bg_color == "#1E1E1E"
    assert config.custom_font_color == "#D4D4D4"
    assert config.display_mode == "reading"
    assert config.zoom_level == 100
    assert config.window_width == 1200
    assert config.window_height == 800
    assert config.window_x == 100
    assert config.window_y == 100
    assert config.last_opened_file == ""
    assert config.render_dpi == 150


def test_save_and_load_config(tmp_path):
    config_path = tmp_path / "config.json"
    config = AppConfig(theme="sepia", zoom_level=150)
    save_config(config, config_path)
    loaded = load_config(config_path)
    assert loaded.theme == "sepia"
    assert loaded.zoom_level == 150
    assert loaded.display_mode == "reading"


def test_load_missing_file_returns_defaults(tmp_path):
    config_path = tmp_path / "nonexistent.json"
    config = load_config(config_path)
    assert config.theme == "dark"
    assert config.zoom_level == 100


def test_load_corrupted_file_returns_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("not valid json {{{")
    config = load_config(config_path)
    assert config.theme == "dark"


def test_load_partial_config_fills_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"theme": "light"}))
    config = load_config(config_path)
    assert config.theme == "light"
    assert config.zoom_level == 100
    assert config.render_dpi == 150


def test_config_roundtrip_preserves_all_fields(tmp_path):
    config_path = tmp_path / "config.json"
    original = AppConfig(
        theme="custom",
        custom_bg_color="#112233",
        custom_font_color="#AABBCC",
        display_mode="faithful",
        zoom_level=200,
        window_width=800,
        window_height=600,
        window_x=50,
        window_y=50,
        last_opened_file="C:/test/doc.pdf",
        render_dpi=120,
    )
    save_config(original, config_path)
    loaded = load_config(config_path)
    assert loaded.theme == original.theme
    assert loaded.custom_bg_color == original.custom_bg_color
    assert loaded.custom_font_color == original.custom_font_color
    assert loaded.display_mode == original.display_mode
    assert loaded.zoom_level == original.zoom_level
    assert loaded.window_width == original.window_width
    assert loaded.window_height == original.window_height
    assert loaded.window_x == original.window_x
    assert loaded.window_y == original.window_y
    assert loaded.last_opened_file == original.last_opened_file
    assert loaded.render_dpi == original.render_dpi
