"""Application configuration: load, save, and defaults."""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AppConfig:
    theme: str = "dark"
    custom_bg_color: str = "#1E1E1E"
    custom_font_color: str = "#D4D4D4"
    display_mode: str = "reading"
    zoom_level: int = 100
    window_width: int = 1200
    window_height: int = 800
    window_x: int = 100
    window_y: int = 100
    last_opened_file: str = ""
    render_dpi: int = 150
    sidebar_collapsed: bool = False


def get_appdata_dir() -> Path:
    """Return %APPDATA%/PDFViewer, creating it if needed."""
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = appdata / "PDFViewer"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    """Return path to config.json in AppData."""
    return get_appdata_dir() / "config.json"


def load_config(path: Path) -> AppConfig:
    """Load config from JSON file. Returns defaults on any error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults = asdict(AppConfig())
        merged = {**defaults, **{k: v for k, v in data.items() if k in defaults}}
        return AppConfig(**merged)
    except (FileNotFoundError, json.JSONDecodeError, TypeError, KeyError):
        return AppConfig()


def save_config(config: AppConfig, path: Path) -> None:
    """Save config to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
