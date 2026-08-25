import json
import re
import subprocess
import sys
import time
from pathlib import Path

from ..models import CollectorResult, RawItem, ScanContext
from .base import Collector

_PS_DIR = Path(__file__).parent.parent / "ps"
_HW_SCRIPT = _PS_DIR / "hardware.ps1"
_FW_SCRIPT = _PS_DIR / "firmware.ps1"

_PCI_RE = re.compile(r"VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})", re.I)
_USB_RE = re.compile(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", re.I)

_PNP_CLASS_MAP = {
    "net":         lambda pnp: "wifi" if "PCI\\" in pnp else "nic",
    "bluetooth":   lambda _: "bluetooth",
    "media":       lambda _: "audio",
    "hdaudio":     lambda _: "audio",
    "scsiadapter": lambda _: "storage",
}
_INTERESTING_PNP_CLASSES = set(_PNP_CLASS_MAP)

# Printers are collected from Win32_Printer (not PnP — USBPRINT IDs carry no VID_/DEV_).
# Names containing these strings are virtual/software printers; skip them.
_VIRTUAL_PRINTER_RE = re.compile(
    r"(microsoft|onenote|adobe pdf|print to pdf|fax|xps|snagit|cutepdf|bullzip|dopdf)", re.I
)

# Printer brand name prefix → USB vendor ID for hardware-table lookup.
_BRAND_VID: dict[str, str] = {
    "HP":      "03F0",
    "Canon":   "04A9",
    "Epson":   "04B8",
    "Brother": "04F9",
    "Lexmark": "043D",
    "Xerox":   "0924",
    "Ricoh":   "05CA",
    "Kyocera": "0482",
    "Samsung": "04E8",
    "Pantum":  "232B",
}


def _printer_brand_vid(name: str) -> str | None:
    upper = name.upper()
    for brand, vid in _BRAND_VID.items():
        if upper.startswith(brand.upper()):
            return vid
    return None


def _pci_ids(pnp: str) -> tuple[str | None, str | None]:
    m = _PCI_RE.search(pnp)
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def _usb_ids(pnp: str) -> tuple[str | None, str | None]:
    m = _USB_RE.search(pnp)
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def run_ps_script(script: Path, timeout: int = 60) -> dict:
    result = subprocess.run(
        ["powershell.exe", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script)],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def parse_hardware_data(hw: dict, fw: dict) -> tuple[list[RawItem], list[str]]:
    """
    Convert raw PowerShell JSON dicts to RawItems.
    Pure data transformation — pass fixtures in tests instead of running PS.
    """
    items: list[RawItem] = []
    warnings: list[str] = []

    for gpu in hw.get("GPUs", []):
        pnp = gpu.get("PNPDeviceID", "")
        ven, dev = _pci_ids(pnp)
        items.append(RawItem(
            source="hardware",
            raw_name=gpu.get("Name", "Unknown GPU"),
            raw_keys={"class": "gpu", "vendor_id": ven, "device_id": dev, "pnp": pnp},
        ))

    for dev in hw.get("PnPDevices", []):
        pnp = dev.get("PNPDeviceID", "")
        cls = (dev.get("Class") or "").lower()
        if cls not in _INTERESTING_PNP_CLASSES:
            continue
        ven, device_id = _pci_ids(pnp)
        if not ven:
            ven, device_id = _usb_ids(pnp)
        if not ven:
            continue
        hw_class = _PNP_CLASS_MAP[cls](pnp)
        items.append(RawItem(
            source="hardware",
            raw_name=dev.get("Name", "Unknown device"),
            raw_keys={"class": hw_class, "vendor_id": ven, "device_id": device_id, "pnp": pnp},
        ))

    for printer in hw.get("Printers", []):
        name = printer.get("Name", "")
        if not name or _VIRTUAL_PRINTER_RE.search(name):
            continue
        items.append(RawItem(
            source="hardware",
            raw_name=name,
            raw_keys={"class": "printer", "vendor_id": _printer_brand_vid(name), "device_id": None},
        ))

    items.append(RawItem(
        source="firmware",
        raw_name="Firmware / boot configuration",
        raw_keys={
            "secure_boot":    fw.get("SecureBoot"),
            "bitlocker":      fw.get("BitLocker"),
            "storage_mode":   fw.get("StorageMode"),
            "disk_style":     fw.get("DiskStyle"),
            "free_gb":        fw.get("FreeGB"),
            "disk_total_gb":  fw.get("DiskTotalGB"),
            "unallocated_gb": fw.get("UnallocatedGB"),
            "partitions": [
                {
                    "size_gb":      p.get("SizeGB"),
                    "type":         p.get("Type"),
                    "drive_letter": p.get("DriveLetter"),
                    "free_gb":      p.get("FreeGB"),
                }
                for p in (fw.get("Partitions") or [])
            ],
        },
    ))

    return items, warnings


class HardwareCollector(Collector):
    id = "hardware"
    display_name = "Hardware & Firmware"
    requires_admin = False

    def available(self) -> bool:
        return sys.platform == "win32" and _HW_SCRIPT.exists()

    def collect(self, ctx: ScanContext) -> CollectorResult:
        t0 = time.monotonic()
        warnings: list[str] = []

        try:
            hw = run_ps_script(_HW_SCRIPT, timeout=ctx.timeout_hardware)
        except Exception as exc:
            hw = {}
            warnings.append(f"Hardware script failed: {exc}")

        try:
            fw = run_ps_script(_FW_SCRIPT, timeout=30)
        except Exception as exc:
            fw = {}
            warnings.append(f"Firmware script failed: {exc}")

        items, parse_warnings = parse_hardware_data(hw, fw)
        warnings.extend(parse_warnings)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CollectorResult(
            id=self.id,
            status="partial" if warnings else "ok",
            duration_ms=duration_ms,
            warnings=warnings,
            items=items,
        )
