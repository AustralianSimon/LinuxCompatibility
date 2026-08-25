"""
pci.ids ingest.

Downloads the public pci.ids vendor/device name database and inserts
vendor-level catchall rows into the hardware table for well-known Linux-supported
hardware classes. device_id = NULL means "any device from this vendor".

The support level and driver are curated here based on known Linux kernel/driver
support. pci.ids itself only provides human-readable names.

Curated YAML overrides (applied after this step) always take precedence.
"""
import requests

_PCIIDS_URL = "https://pci-ids.ucw.cz/v2.2/pci.ids"
_UA = "linuxready-harvester/0.1 (github.com/AustralianSimon/LinuxCompatibility)"

# (vendor_id, hw_class, support, driver, description)
# support values must match _SUPPORT_TO_VERDICT in verdict/rules.py:
#   excellent/good → native  |  needs_setup → layer_workable  |  poor → layer_poor
_KNOWN_HW: list[tuple[str, str, str, str, str]] = [
    # GPUs
    ("10DE", "gpu",       "good",        "nvidia",         "NVIDIA GPU"),
    ("1002", "gpu",       "excellent",   "amdgpu",         "AMD GPU"),
    ("8086", "gpu",       "excellent",   "i915",           "Intel GPU"),
    # WiFi
    ("8086", "wifi",      "excellent",   "iwlwifi",        "Intel WiFi"),
    ("168C", "wifi",      "good",        "ath11k",         "Qualcomm/Atheros WiFi"),
    ("10EC", "wifi",      "good",        "rtw89",          "Realtek WiFi"),
    ("0BDA", "wifi",      "good",        "rtl8xxxu",       "Realtek USB WiFi"),
    ("14E4", "wifi",      "needs_setup", "broadcom-sta",   "Broadcom WiFi"),
    # Audio
    ("8086", "audio",     "excellent",   "snd_hda_intel",  "Intel HD Audio"),
    ("10EC", "audio",     "excellent",   "snd_hda_intel",  "Realtek HD Audio"),
    ("1002", "audio",     "excellent",   "snd_hda_intel",  "AMD HD Audio"),
    # Bluetooth
    ("8086", "bluetooth", "excellent",   "btintel",        "Intel Bluetooth"),
    ("0A12", "bluetooth", "good",        "btusb",          "CSR Bluetooth"),
    # Storage controllers
    ("8086", "storage",   "excellent",   "ahci",           "Intel SATA/NVMe"),
    ("1022", "storage",   "excellent",   "ahci",           "AMD SATA/NVMe"),
    ("144D", "storage",   "excellent",   "nvme",           "Samsung NVMe"),
    ("15B7", "storage",   "excellent",   "nvme",           "WD/SanDisk NVMe"),
    ("1987", "storage",   "excellent",   "nvme",           "Phison NVMe"),
    # Printers (USB vendor IDs — support via CUPS/HPLIP/official drivers)
    ("03F0", "printer",   "excellent",   "hplip",          "HP Printer"),
    ("04F9", "printer",   "excellent",   "cups",           "Brother Printer"),
    ("04A9", "printer",   "good",        "cups",           "Canon Printer"),
    ("04B8", "printer",   "good",        "epson-inkjet",   "Epson Printer"),
    ("043D", "printer",   "good",        "cups",           "Lexmark Printer"),
    ("0924", "printer",   "good",        "cups",           "Xerox Printer"),
    ("05CA", "printer",   "good",        "cups",           "Ricoh Printer"),
    ("0482", "printer",   "good",        "cups",           "Kyocera Printer"),
    ("04E8", "printer",   "needs_setup", "cups",           "Samsung Printer"),
]


# ── pure parsers (I/O-free, testable) ──────────────────────────────────────

def parse_pci_ids(text: str) -> dict[str, str]:
    """
    Parse pci.ids file text and return a {VENDOR_ID_UPPER: vendor_name} dict.
    Only top-level vendor lines are parsed (device and subsystem lines are skipped).
    """
    vendors: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or line.startswith("\t"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 4:
            continue
        try:
            int(parts[0], 16)
        except ValueError:
            continue
        vendors[parts[0].upper()] = parts[1].strip()
    return vendors


def build_hardware_rows(
    vendor_names: dict[str, str],
) -> list[tuple]:
    """
    Combine _KNOWN_HW rules with pci.ids vendor names to produce rows ready for
    INSERT into the hardware table:
    (vendor_id, device_id, class, driver, support, min_kernel, notes)
    """
    rows = []
    for vendor_id, hw_class, support, driver, description in _KNOWN_HW:
        vendor_name = vendor_names.get(vendor_id, "")
        notes = f"{description} ({vendor_name})" if vendor_name else description
        rows.append((vendor_id, None, hw_class, driver, support, None, notes))
    return rows


# ── network + ingest ────────────────────────────────────────────────────────

def ingest_pci_ids(conn) -> int:
    """
    Download pci.ids, parse vendor names, and insert vendor-level hardware rows.
    Uses INSERT OR IGNORE so curated overrides applied afterwards are never lost.
    Returns the number of rows inserted.
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    print("  Downloading pci.ids…", flush=True)
    resp = session.get(_PCIIDS_URL, timeout=60)
    resp.raise_for_status()

    vendor_names = parse_pci_ids(resp.text)
    print(f"  pci.ids: {len(vendor_names):,} vendors parsed", flush=True)

    rows = build_hardware_rows(vendor_names)
    inserted = 0
    for row in rows:
        result = conn.execute(
            "INSERT OR IGNORE INTO hardware "
            "(vendor_id, device_id, class, driver, support, min_kernel, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        inserted += result.rowcount

    conn.commit()
    print(f"  pci.ids: {inserted} hardware rows inserted", flush=True)
    return inserted
