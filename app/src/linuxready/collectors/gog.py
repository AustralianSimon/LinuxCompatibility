"""
GOG Galaxy collector.
Reads installed game entries from the Windows registry.
GOG registers games at HKLM\\SOFTWARE\\WOW6432Node\\GOG.com\\Games\\{productId}.
"""
import sys
import time
from typing import Any

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_GOG_KEY = r"SOFTWARE\WOW6432Node\GOG.com\Games"


def parse_gog_entries(entries: list[dict[str, Any]]) -> tuple[list[RawItem], list[str]]:
    """Parse a list of GOG registry entry dicts into RawItems."""
    items = []
    for entry in entries:
        name = (entry.get("GAMENAME") or "").strip()
        if not name:
            continue
        items.append(RawItem(
            source="gog",
            raw_name=name,
            raw_keys={
                "gog_product_id": entry.get("productid"),
                "publisher": entry.get("publisher"),
            },
        ))
    return items, []


def read_gog_registry() -> tuple[list[dict[str, Any]], list[str]]:
    """Read GOG game entries from the Windows registry."""
    try:
        import winreg
    except ImportError:
        return [], ["winreg not available (not running on Windows)"]

    entries = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GOG_KEY) as gog_key:
            idx = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(gog_key, idx)
                    idx += 1
                    try:
                        with winreg.OpenKey(gog_key, subkey_name) as subkey:
                            entry: dict[str, Any] = {}
                            for value_name in ("GAMENAME", "productid", "publisher"):
                                try:
                                    val, _ = winreg.QueryValueEx(subkey, value_name)
                                    entry[value_name] = val
                                except FileNotFoundError:
                                    pass
                            if entry:
                                entries.append(entry)
                    except OSError:
                        continue
                except OSError:
                    break
    except FileNotFoundError:
        return [], [f"GOG registry key not found: {_GOG_KEY}"]
    except OSError as exc:
        return [], [f"Failed to read GOG registry: {exc}"]

    return entries, []


class GogCollector(Collector):
    id = "gog"
    display_name = "GOG Games"
    requires_admin = False

    def available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GOG_KEY):
                return True
        except Exception:
            return False

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        entries, read_warnings = read_gog_registry()
        items, parse_warnings = parse_gog_entries(entries)
        warnings = read_warnings + parse_warnings
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="partial" if warnings else "ok",
            duration_ms=duration_ms,
            warnings=warnings,
            items=items,
        )
