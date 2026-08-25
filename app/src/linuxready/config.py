import os
from pathlib import Path

APP_NAME = "LinuxReadyAmI"
SCHEMA_VERSION = "1.0"
GITHUB_REPO = "AustralianSimon/LinuxCompatibility"

_local = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")).expanduser()
APP_DATA_DIR = _local / "LinuxReady"
SCANS_DIR = APP_DATA_DIR / "scans"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"

_here = Path(__file__).parent
DB_PATH = Path(os.environ.get("LINUXREADY_DB", str(_here / "db" / "compat.db")))
PS_DIR = _here / "ps"

COLLECTOR_TIMEOUT_DEFAULT = 30
COLLECTOR_TIMEOUT_HARDWARE = 60

READINESS_WEIGHTS: dict[str, float] = {"hw": 0.4, "apps": 0.35, "games": 0.25}

VERDICTS_PASS = frozenset({"native", "packaged", "layer_excellent", "web"})
VERDICTS_PARTIAL = frozenset({"layer_workable"})
VERDICTS_FAIL = frozenset({"layer_poor", "blocked", "replace"})
VERDICTS_UNKNOWN = frozenset({"unknown"})

ACCENT_COLOR = "#00B4D8"
DEFAULT_THEME = "dark"
