import re
import time
from pathlib import Path

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector


def _parse_vdf(text: str) -> dict:
    """Parse Valve KeyValues1 text into a nested dict."""
    stack: list[dict] = [{}]
    key: str | None = None
    for quoted, brace in re.findall(r'"((?:[^"\\]|\\.)*)"|([\{\}])', text):
        if quoted:
            if key is None:
                key = quoted
            else:
                stack[-1][key] = quoted
                key = None
        elif brace == "{":
            node: dict = {}
            if key is not None:
                stack[-1][key] = node
                key = None
            stack.append(node)
        elif brace == "}":
            child = stack.pop()
            if not stack:
                return child
    return stack[0]


def parse_library_folders(vdf_text: str) -> list[Path]:
    """Return Steam library roots from a libraryfolders.vdf string."""
    data = _parse_vdf(vdf_text)
    root = data.get("libraryfolders", data)
    paths: list[Path] = []
    for v in root.values():
        if isinstance(v, dict) and "path" in v:
            paths.append(Path(v["path"]))
    return paths


def parse_app_manifest(acf_text: str) -> dict | None:
    """Parse an appmanifest_*.acf string. Returns None if missing required fields."""
    data = _parse_vdf(acf_text)
    state = data.get("AppState", {})
    appid = state.get("appid")
    name = state.get("name")
    if not appid or not name:
        return None
    return {
        "appid": int(appid),
        "name": name,
        "size_on_disk": int(state.get("SizeOnDisk", 0)),
        "last_played": int(state.get("LastPlayed", 0)),
    }


def find_steam_root() -> Path | None:
    """Locate the Steam installation directory via the Windows registry."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            path, _ = winreg.QueryValueEx(k, "SteamPath")
            return Path(path)
    except Exception:
        return None


def collect_steam_items(steam_root: Path) -> tuple[list[RawItem], list[str]]:
    """
    Read library folders and app manifests under steam_root.
    Pure filesystem access — seam for testing: pass any Path with the right layout.
    """
    warnings: list[str] = []
    items: list[RawItem] = []

    lf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if not lf_path.exists():
        return items, [f"libraryfolders.vdf not found: {lf_path}"]

    extra_roots = parse_library_folders(lf_path.read_text(encoding="utf-8", errors="replace"))
    library_dirs = [steam_root / "steamapps"] + [p / "steamapps" for p in extra_roots]

    seen: set[Path] = set()
    for lib in library_dirs:
        resolved = lib.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not lib.is_dir():
            warnings.append(f"Library directory not found: {lib}")
            continue
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                manifest = parse_app_manifest(acf.read_text(encoding="utf-8", errors="replace"))
                if manifest:
                    items.append(RawItem(
                        source="steam",
                        raw_name=manifest["name"],
                        raw_keys={
                            "steam_appid": manifest["appid"],
                            "size_on_disk": manifest["size_on_disk"],
                            "last_played": manifest["last_played"],
                        },
                    ))
            except Exception as exc:
                warnings.append(f"Failed to parse {acf.name}: {exc}")

    return items, warnings


class SteamCollector(Collector):
    id = "steam"
    display_name = "Steam Games"
    requires_admin = False

    def available(self) -> bool:
        return find_steam_root() is not None

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        steam_root = find_steam_root()
        if steam_root is None:
            return CollectorResult(id=self.id, status="skipped", duration_ms=0,
                                   warnings=["Steam installation not found"])

        items, warnings = collect_steam_items(steam_root)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="partial" if warnings else "ok",
            duration_ms=duration_ms,
            warnings=warnings,
            items=items,
        )
