import sys
import time

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_UNINSTALL_SUBKEYS = [
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",         "HKLM"),
    (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",         "HKCU"),
]

_STR_VALUES = {"DisplayName", "Publisher", "DisplayVersion", "InstallDate",
               "InstallLocation", "ParentKeyName"}
_DWORD_VALUES = {"SystemComponent"}


def parse_uninstall_entries(entries: list[dict]) -> tuple[list[RawItem], list[str]]:
    """
    Filter and convert raw registry dicts to RawItems.
    Pure data transformation — no Windows API calls. Safe to call in tests.
    """
    items: list[RawItem] = []
    for entry in entries:
        name = entry.get("DisplayName", "").strip()
        if not name:
            continue
        if entry.get("SystemComponent") == "1":
            continue
        if entry.get("ParentKeyName"):
            continue
        items.append(RawItem(
            source="registry_apps",
            raw_name=name,
            raw_keys={
                "publisher": entry.get("Publisher", "").strip() or None,
                "version": entry.get("DisplayVersion", "").strip() or None,
            },
        ))
    return items, []


def read_registry_entries() -> list[dict]:
    """Enumerate Uninstall keys from the Windows registry. Requires winreg (Windows only)."""
    import winreg

    root_map = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
    }
    entries: list[dict] = []

    for subkey, root_name in _UNINSTALL_SUBKEYS:
        root = root_map[root_name]
        try:
            with winreg.OpenKey(root, subkey,
                                access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                count = winreg.QueryInfoKey(k)[0]
                for i in range(count):
                    try:
                        sub_name = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, sub_name) as sk:
                            entry: dict = {}
                            for val in _STR_VALUES:
                                try:
                                    entry[val], _ = winreg.QueryValueEx(sk, val)
                                except FileNotFoundError:
                                    pass
                            for val in _DWORD_VALUES:
                                try:
                                    v, _ = winreg.QueryValueEx(sk, val)
                                    entry[val] = str(v)
                                except FileNotFoundError:
                                    pass
                            entries.append(entry)
                    except Exception:
                        pass
        except Exception:
            pass

    return entries


class RegistryAppsCollector(Collector):
    id = "registry_apps"
    display_name = "Installed Applications"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32"

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        try:
            raw = read_registry_entries()
            items, warnings = parse_uninstall_entries(raw)
            status = "ok"
        except Exception as exc:
            items, warnings, status = [], [str(exc)], "failed"
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(id=self.id, status=status, duration_ms=duration_ms,
                               warnings=warnings, items=items)
