"""
Epic Games collector.
Reads .item manifest JSON files from the Epic Games Launcher data directory.
"""
import json
import sys
import time
from pathlib import Path

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_MANIFESTS_DIR = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")


def parse_epic_manifests(manifests: list[dict]) -> tuple[list[RawItem], list[str]]:
    """
    Parse a list of Epic manifest dicts into RawItems.
    Filters out non-game entries (AppCategories without 'games') and entries
    with missing or empty DisplayName.
    """
    items = []
    for manifest in manifests:
        name = (manifest.get("DisplayName") or "").strip()
        if not name:
            continue
        categories = manifest.get("AppCategories") or []
        if not any("games" in cat.lower() for cat in categories):
            continue
        items.append(RawItem(
            source="epic",
            raw_name=name,
            raw_keys={
                "catalog_item_id": manifest.get("CatalogItemId"),
                "catalog_namespace": manifest.get("CatalogNamespace"),
                "app_name": manifest.get("AppName"),
            },
        ))
    return items, []


def read_epic_manifests(manifests_dir: Path) -> tuple[list[dict], list[str]]:
    """Read all .item manifest JSON files from manifests_dir."""
    if not manifests_dir.is_dir():
        return [], [f"Epic manifests directory not found: {manifests_dir}"]

    manifests = []
    warnings = []
    for item_file in manifests_dir.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            manifests.append(data)
        except Exception as exc:
            warnings.append(f"Failed to parse {item_file.name}: {exc}")
    return manifests, warnings


class EpicCollector(Collector):
    id = "epic"
    display_name = "Epic Games"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32" and _MANIFESTS_DIR.is_dir()

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        manifests, read_warnings = read_epic_manifests(_MANIFESTS_DIR)
        items, parse_warnings = parse_epic_manifests(manifests)
        warnings = read_warnings + parse_warnings
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="partial" if warnings else "ok",
            duration_ms=duration_ms,
            warnings=warnings,
            items=items,
        )
