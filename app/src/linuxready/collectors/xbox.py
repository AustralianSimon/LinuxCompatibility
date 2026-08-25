"""
Xbox / Game Pass collector.
Discovers installed Game Pass titles by scanning the Xbox games install directory
for MicrosoftGame.config (Win32 titles) and AppxManifest.xml (UWP titles).
"""
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_DEFAULT_GAMES_DIR = Path(r"C:\XboxGames")

# XML namespaces
_MSGC_NS = "http://schemas.microsoft.com/Gaming/2018/06/MicrosoftGameConfig"
_APPX_NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"


def parse_microsoft_game_config(xml_text: str) -> dict | None:
    """
    Parse a MicrosoftGame.config file.
    Returns None when the display name is missing, empty, or an unresolvable
    ms-resource: string (requires native Windows APIs to resolve).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Namespace may or may not be present in older configs
    elem = root.find(f"{{{_MSGC_NS}}}DisplayName")
    if elem is None:
        elem = root.find("DisplayName")
    name = (elem.text or "").strip() if elem is not None else ""
    if not name or name.startswith("ms-resource:"):
        return None

    id_elem = root.find(f"{{{_MSGC_NS}}}Identity")
    if id_elem is None:
        id_elem = root.find("Identity")
    pkg_name = (id_elem.get("Name") or "").strip() if id_elem is not None else ""

    return {"name": name, "package_name": pkg_name or None}


def parse_appx_manifest(xml_text: str) -> dict | None:
    """
    Parse an AppxManifest.xml file.
    Returns None when the display name is missing, empty, or an unresolvable
    ms-resource: string.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    elem = root.find(f"{{{_APPX_NS}}}Properties/{{{_APPX_NS}}}DisplayName")
    if elem is None:
        elem = root.find("Properties/DisplayName")
    name = (elem.text or "").strip() if elem is not None else ""
    if not name or name.startswith("ms-resource:"):
        return None

    id_elem = root.find(f"{{{_APPX_NS}}}Identity")
    if id_elem is None:
        id_elem = root.find("Identity")
    pkg_name = (id_elem.get("Name") or "").strip() if id_elem is not None else ""

    return {"name": name, "package_name": pkg_name or None}


def read_game_dir(game_dir: Path) -> dict | None:
    """
    Read game metadata from a single Xbox game install directory.
    Looks for MicrosoftGame.config first, then AppxManifest.xml, under
    the Content/ subdirectory (and game_dir root as fallback).
    Returns None if no resolvable name is found.
    """
    search_dirs = [game_dir / "Content", game_dir]
    for search in search_dirs:
        config = search / "MicrosoftGame.config"
        if config.is_file():
            try:
                result = parse_microsoft_game_config(config.read_text(encoding="utf-8", errors="replace"))
                if result:
                    return result
            except OSError:
                pass

        manifest = search / "AppxManifest.xml"
        if manifest.is_file():
            try:
                result = parse_appx_manifest(manifest.read_text(encoding="utf-8", errors="replace"))
                if result:
                    return result
            except OSError:
                pass

    return None


def collect_xbox_items(games_dir: Path) -> tuple[list[RawItem], list[str]]:
    """
    Scan games_dir for installed Xbox / Game Pass titles.
    Each immediate subdirectory is treated as a potential game install.
    Pure filesystem access — seam for testing: pass any Path.
    """
    if not games_dir.is_dir():
        return [], [f"Xbox games directory not found: {games_dir}"]

    items: list[RawItem] = []
    warnings: list[str] = []

    for game_dir in sorted(games_dir.iterdir()):
        if not game_dir.is_dir():
            continue
        try:
            info = read_game_dir(game_dir)
        except Exception as exc:
            warnings.append(f"Failed to read {game_dir.name}: {exc}")
            continue
        if info is None:
            continue
        items.append(RawItem(
            source="xbox",
            raw_name=info["name"],
            raw_keys={"package_name": info.get("package_name")},
        ))

    return items, warnings


class XboxCollector(Collector):
    id = "xbox"
    display_name = "Xbox / Game Pass"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32" and _DEFAULT_GAMES_DIR.is_dir()

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        items, warnings = collect_xbox_items(_DEFAULT_GAMES_DIR)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="partial" if warnings else "ok",
            duration_ms=duration_ms,
            warnings=warnings,
            items=items,
        )
