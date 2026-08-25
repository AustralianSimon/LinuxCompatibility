"""Persistent user settings, stored in APP_DATA_DIR/settings.json."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DEFAULT_THEME, SETTINGS_FILE


@dataclass
class Settings:
    theme: str = DEFAULT_THEME   # dark | light | auto
    portable_scan: bool = False


def load_settings(path: Path | None = None) -> Settings:
    path = path or SETTINGS_FILE
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Settings(
            theme=data.get("theme", DEFAULT_THEME),
            portable_scan=bool(data.get("portable_scan", False)),
        )
    except Exception:
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
