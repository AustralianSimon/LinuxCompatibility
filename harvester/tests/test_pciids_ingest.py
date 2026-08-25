"""Tests for the pci.ids ingest parser."""
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harvester.sources.pciids import parse_pci_ids, build_hardware_rows, ingest_pci_ids

_SCHEMA = (
    Path(__file__).parent.parent.parent
    / "app" / "src" / "linuxready" / "db" / "schema.sql"
)

_SAMPLE_PCIIDS = """\
# PCI ID database
# Maintained by Martin Mares <mj@ucw.cz>

0000  Illegal Vendor
0001  SafeNet (wrong ID)
1002  Advanced Micro Devices, Inc. [AMD/ATI]
\t687f  Vega 10 XL/XT [Radeon RX Vega 56/64]
\t\t1043 0555  ROG STRIX VEGA64 O8G Gaming
10de  NVIDIA Corporation
\t2204  GA102 [GeForce RTX 3090]
8086  Intel Corporation
\t1901  6th-10th Gen Core Processor PCIe Controller
10ec  Realtek Semiconductor Co., Ltd.
\t8168  RTL8111/8168/8411 PCI Express Gigabit Ethernet
14e4  Broadcom Inc. and subsidiaries
168c  Qualcomm Atheros
0bda  Realtek Semiconductor Corp.
0a12  Cambridge Silicon Radio, Ltd
144d  Samsung Electronics Co Ltd
15b7  Sandisk Corp
1987  Phison Electronics Corporation
1022  Advanced Micro Devices, Inc. [AMD]
"""


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


# ── parse_pci_ids ────────────────────────────────────────────────────────────

def test_parses_vendor_names():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    assert result["10DE"] == "NVIDIA Corporation"
    assert result["8086"] == "Intel Corporation"
    assert result["1002"] == "Advanced Micro Devices, Inc. [AMD/ATI]"

def test_vendor_ids_are_uppercase():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    assert "10DE" in result
    assert "10de" not in result

def test_skips_device_lines():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    assert "687f" not in result  # device ID, not a vendor

def test_skips_comment_lines():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    # Comments start with #
    assert len(result) > 0
    for key in result:
        assert not key.startswith("#")

def test_empty_input_returns_empty():
    assert parse_pci_ids("") == {}

def test_realtek_parsed():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    assert "10EC" in result

def test_broadcom_parsed():
    result = parse_pci_ids(_SAMPLE_PCIIDS)
    assert "14E4" in result


# ── build_hardware_rows ───────────────────────────────────────────────────────

def test_rows_have_correct_tuple_length():
    rows = build_hardware_rows({"10DE": "NVIDIA Corporation"})
    assert all(len(r) == 7 for r in rows)

def test_rows_include_nvidia_gpu():
    rows = build_hardware_rows({"10DE": "NVIDIA Corporation"})
    nvidia_gpu = [r for r in rows if r[0] == "10DE" and r[2] == "gpu"]
    assert len(nvidia_gpu) == 1

def test_rows_include_amd_gpu():
    rows = build_hardware_rows({"1002": "AMD"})
    amd_gpu = [r for r in rows if r[0] == "1002" and r[2] == "gpu"]
    assert len(amd_gpu) == 1
    assert amd_gpu[0][4] == "excellent"

def test_device_id_is_none_for_catchall_rows():
    rows = build_hardware_rows({})
    assert all(r[1] is None for r in rows)

def test_vendor_name_included_in_notes():
    rows = build_hardware_rows({"10DE": "NVIDIA Corporation"})
    nvidia_gpu = next(r for r in rows if r[0] == "10DE" and r[2] == "gpu")
    assert "NVIDIA Corporation" in nvidia_gpu[6]

def test_broadcom_wifi_is_needs_setup():
    rows = build_hardware_rows({})
    broadcom = next(r for r in rows if r[0] == "14E4" and r[2] == "wifi")
    assert broadcom[4] == "needs_setup"

def test_intel_wifi_is_excellent():
    rows = build_hardware_rows({})
    intel_wifi = next(r for r in rows if r[0] == "8086" and r[2] == "wifi")
    assert intel_wifi[4] == "excellent"


# ── DB integration ────────────────────────────────────────────────────────────

def test_rows_inserted_into_hardware_table():
    conn = _db()
    vendor_names = parse_pci_ids(_SAMPLE_PCIIDS)
    rows = build_hardware_rows(vendor_names)
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO hardware "
            "(vendor_id, device_id, class, driver, support, min_kernel, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM hardware").fetchone()[0]
    assert count == len(rows)

def test_insert_or_ignore_does_not_overwrite_existing():
    conn = _db()
    conn.execute(
        "INSERT INTO hardware (vendor_id, device_id, class, driver, support, notes) "
        "VALUES ('10DE', NULL, 'gpu', 'custom', 'unsupported', 'curated override')"
    )
    conn.commit()
    rows = build_hardware_rows({"10DE": "NVIDIA"})
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO hardware "
            "(vendor_id, device_id, class, driver, support, min_kernel, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    row = conn.execute(
        "SELECT support, notes FROM hardware WHERE vendor_id='10DE' AND device_id IS NULL AND class='gpu'"
    ).fetchone()
    assert row[0] == "unsupported"
    assert row[1] == "curated override"
