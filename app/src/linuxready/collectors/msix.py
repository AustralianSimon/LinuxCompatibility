import json
import re
import subprocess
import sys
import time
from pathlib import Path

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_PS_SCRIPT = Path(__file__).parent.parent / "ps" / "appx.ps1"

_NOISE_PATTERNS = re.compile(
    r"WinAppRuntime|DDLM\.|VCLibs|NativeFramework", re.IGNORECASE
)


def parse_appx_packages(packages: list[dict]) -> tuple[list[RawItem], list[str]]:
    """
    Filter raw Get-AppxPackage output to real user apps and convert to RawItems.
    Pure data transformation — no Windows or subprocess calls.
    """
    items: list[RawItem] = []
    for pkg in packages:
        display_name = pkg.get("DisplayName") or ""
        if not display_name or display_name.startswith("ms-resource:"):
            continue
        pkg_name = pkg.get("PackageName") or ""
        if _NOISE_PATTERNS.search(pkg_name):
            continue
        items.append(RawItem(
            source="msix",
            raw_name=display_name,
            raw_keys={
                "publisher":    pkg.get("Publisher") or None,
                "version":      pkg.get("Version") or None,
                "package_name": pkg_name or None,
            },
        ))
    return items, []


def run_appx_packages() -> list[dict]:
    """Run the PowerShell script and return parsed JSON. Windows only."""
    result = subprocess.run(
        ["powershell.exe", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(_PS_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"appx.ps1 exited {result.returncode}: {result.stderr.strip()}")
    output = result.stdout.strip()
    if not output:
        return []
    data = json.loads(output)
    return data if isinstance(data, list) else [data]


class MsixCollector(Collector):
    id = "msix"
    display_name = "Microsoft Store Apps"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32" and _PS_SCRIPT.exists()

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        try:
            raw = run_appx_packages()
            items, warnings = parse_appx_packages(raw)
            status = "ok"
        except Exception as exc:
            items, warnings, status = [], [str(exc)], "failed"
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(id=self.id, status=status, duration_ms=duration_ms,
                               warnings=warnings, items=items)
