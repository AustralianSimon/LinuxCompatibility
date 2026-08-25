"""
Local user verdict overrides.

Users edit  %APPDATA%/LinuxReadyAmI/overrides.yaml  (or the path returned by
default_overrides_path()) to correct wrong verdicts without waiting for a DB
update.  The file is keyed by matched_id (the app_id / steam_appid string that
the matcher resolves to).

To share a correction with the community, copy the entry and open a PR against
harvester/data/overrides/apps.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import ScanItem

_VALID_VERDICTS = frozenset({
    "native", "packaged", "web",
    "layer_excellent", "layer_workable", "layer_poor",
    "blocked", "replace", "unknown",
})

_HEADER = """\
# LinuxReadyAmI — local verdict overrides
# These take precedence over the compatibility database.
#
# Keys are matched_id values (app_id or steam_appid string).
# To contribute a correction back to the community, open a PR against:
#   harvester/data/overrides/apps.yaml  (for desktop apps)
#   harvester/data/overrides/games.yaml (for Steam games)
#
# Valid verdicts: native, packaged, web, layer_excellent, layer_workable,
#                 layer_poor, blocked, replace, unknown
#
# Example:
#   overrides:
#     adobe.photoshop:
#       verdict: layer_workable
#       note: Works well with Bottles 51.x
"""


def default_overrides_path() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "LinuxReadyAmI" / "overrides.yaml"


def load_user_overrides(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return {matched_id: {verdict, note}} from the overrides file (empty dict if missing)."""
    path = path or default_overrides_path()
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("overrides") or {}
    if not isinstance(entries, dict):
        return {}
    return {k: v for k, v in entries.items() if isinstance(v, dict)}


def apply_user_overrides(
    items: list[ScanItem],
    overrides: dict[str, dict[str, Any]],
) -> None:
    """Patch verdicts in-place for any item whose matched_id appears in overrides."""
    if not overrides:
        return
    for item in items:
        if not item.matched_id or item.matched_id not in overrides:
            continue
        entry = overrides[item.matched_id]
        verdict = entry.get("verdict")
        if verdict not in _VALID_VERDICTS:
            continue
        item.verdict = verdict
        item.is_blocker = (verdict == "blocked")
        note = (entry.get("note") or "").strip()
        tag = f"[User override] {note}" if note else "[User override]"
        item.evidence.insert(0, tag)


def save_user_override(
    matched_id: str,
    verdict: str,
    note: str = "",
    path: Path | None = None,
) -> None:
    """Add or replace a single override entry and write the file."""
    if verdict not in _VALID_VERDICTS:
        raise ValueError(f"Unknown verdict: {verdict!r}")

    path = path or default_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raw = {}

    overrides = raw.get("overrides") or {}
    entry: dict[str, Any] = {"verdict": verdict}
    if note.strip():
        entry["note"] = note.strip()
    overrides[matched_id] = entry
    raw["overrides"] = overrides

    body = yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=True)
    path.write_text(_HEADER + body, encoding="utf-8")


def remove_user_override(matched_id: str, path: Path | None = None) -> bool:
    """Remove an override entry. Returns True if an entry was removed."""
    path = path or default_overrides_path()
    if not path.exists():
        return False
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    overrides = raw.get("overrides") or {}
    if matched_id not in overrides:
        return False
    del overrides[matched_id]
    raw["overrides"] = overrides
    body = yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=True)
    path.write_text(_HEADER + body, encoding="utf-8")
    return True
