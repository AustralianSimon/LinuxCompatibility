"""
User data migration sizing collector.

Measures browser profiles, standard user folders, and mail stores so the
results screen can show the user how much data they would need to move.
Does not go through the matcher/verdict engine — returns MigrationItems directly
via CollectorResult.migration.
"""
import os
import sys
import time
from pathlib import Path

from ..models import CollectorResult, MigrationItem, ScanContext
from .base import Collector

_MAX_FILES = 50_000  # cap file count to keep sizing fast on huge trees


def _dir_size_gb(path: Path) -> float:
    total = count = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass
                count += 1
                if count >= _MAX_FILES:
                    return round(total / 1e9, 3)
    except (PermissionError, OSError):
        pass
    return round(total / 1e9, 3)


def _pst_size_gb(path: Path) -> float:
    total = 0
    for pattern in ("*.pst", "*.ost"):
        for f in path.rglob(pattern):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return round(total / 1e9, 3)


# (label, subdir-relative-to-USERPROFILE, category, note)
_USER_FOLDERS: list[tuple[str, str, str, str]] = [
    ("Documents",  "Documents",  "documents", "Direct copy — works on any distro."),
    ("Downloads",  "Downloads",  "documents", "Direct copy."),
    ("Desktop",    "Desktop",    "documents", "Direct copy."),
    ("Pictures",   "Pictures",   "documents", "Direct copy."),
    ("Music",      "Music",      "documents", "Direct copy."),
    ("Videos",     "Videos",     "documents", "Direct copy."),
]

# (label, path-relative-to-env-var, env-var, category, note)
_BROWSERS: list[tuple[str, str, str, str, str]] = [
    ("Chrome profile",
     "Google\\Chrome\\User Data", "LOCALAPPDATA", "browser",
     "Sign into Chrome on Linux to sync bookmarks, history, and passwords. "
     "Chrome Web Store extensions carry over; paid extensions may need re-purchase."),
    ("Edge profile",
     "Microsoft\\Edge\\User Data", "LOCALAPPDATA", "browser",
     "Edge is available on Linux. Sign in to sync, or export bookmarks via "
     "Settings › Favorites › Export."),
    ("Firefox profile",
     "Mozilla\\Firefox\\Profiles", "APPDATA", "browser",
     "Copy the Profiles folder to ~/.mozilla/firefox/ on Linux — Firefox is "
     "fully cross-platform and the profile format is identical."),
    ("Brave profile",
     "BraveSoftware\\Brave-Browser\\User Data", "LOCALAPPDATA", "browser",
     "Sign into Brave on Linux to sync. Brave Wallet seed phrase will need "
     "re-entry on the Linux side."),
]

# (label, path-relative-to-env-var, env-var, category, note, use_pst_scan)
_MAIL: list[tuple[str, str, str, str, str, bool]] = [
    ("Outlook data",
     "Microsoft\\Outlook", "LOCALAPPDATA", "mail",
     "Export as .pst via File › Open & Export › Import/Export, then import into "
     "Thunderbird using the ImportExportTools NG add-on.",
     True),
    ("Thunderbird profile",
     "Thunderbird\\Profiles", "APPDATA", "mail",
     "Copy the Profiles folder to ~/.thunderbird/ on Linux — the format is identical.",
     False),
]


def collect_migration(env: dict | None = None) -> list[MigrationItem]:
    """
    Measure user data directories and return MigrationItems.
    env defaults to os.environ; pass a dict in tests to avoid touching the real filesystem.
    """
    env = env if env is not None else dict(os.environ)
    items: list[MigrationItem] = []

    userprofile = Path(env.get("USERPROFILE", ""))
    for label, subdir, category, note in _USER_FOLDERS:
        path = userprofile / subdir
        found = path.exists()
        items.append(MigrationItem(
            category=category,
            name=label,
            path=str(path),
            size_gb=_dir_size_gb(path) if found else 0.0,
            note=note,
            found=found,
        ))

    for label, subdir, env_var, category, note in _BROWSERS:
        base = Path(env.get(env_var, ""))
        path = base / subdir
        found = path.exists()
        items.append(MigrationItem(
            category=category,
            name=label,
            path=str(path),
            size_gb=_dir_size_gb(path) if found else 0.0,
            note=note,
            found=found,
        ))

    for label, subdir, env_var, category, note, use_pst in _MAIL:
        base = Path(env.get(env_var, ""))
        path = base / subdir
        found = path.exists()
        size = _pst_size_gb(path) if (found and use_pst) else (
               _dir_size_gb(path) if found else 0.0)
        items.append(MigrationItem(
            category=category,
            name=label,
            path=str(path),
            size_gb=size,
            note=note,
            found=found,
        ))

    return items


class UserdataCollector(Collector):
    id = "userdata"
    display_name = "User data & migration sizing"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32" and bool(os.environ.get("USERPROFILE"))

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        migration = collect_migration()
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="ok",
            duration_ms=duration_ms,
            migration=migration,
        )
