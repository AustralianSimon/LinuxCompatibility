"""Auto-save scan results as versioned JSON under SCANS_DIR."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .config import SCANS_DIR
from .models import ScanResult

_MAX_SAVED = 50   # prune oldest when exceeded


def _serialise(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    raise TypeError(type(obj))


def save_scan(result: ScanResult, scans_dir: Path | None = None) -> Path:
    """Serialise result to JSON and write it to scans_dir. Returns the file path."""
    scans_dir = scans_dir or SCANS_DIR
    scans_dir.mkdir(parents=True, exist_ok=True)

    ts = result.scanned_at.replace(":", "").replace("-", "").replace("+", "")[:15]
    filename = f"scan_{ts}_{result.scan_id[:8]}.json"
    path = scans_dir / filename

    path.write_text(
        json.dumps(dataclasses.asdict(result), indent=2, default=str),
        encoding="utf-8",
    )

    _prune(scans_dir)
    return path


def list_scans(scans_dir: Path | None = None) -> list[Path]:
    """Return saved scan JSON paths, newest first."""
    scans_dir = scans_dir or SCANS_DIR
    if not scans_dir.exists():
        return []
    return sorted(scans_dir.glob("scan_*.json"), reverse=True)


def _prune(scans_dir: Path) -> None:
    scans = sorted(scans_dir.glob("scan_*.json"))
    for old in scans[:-_MAX_SAVED]:
        try:
            old.unlink()
        except OSError:
            pass
