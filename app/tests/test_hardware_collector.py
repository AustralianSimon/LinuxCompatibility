"""Tests for the hardware collector — uses JSON fixtures, no PowerShell."""
import json
from pathlib import Path

from linuxready.collectors.hardware import parse_hardware_data

FIXTURES = Path(__file__).parent / "fixtures"


def _hw():
    return json.loads((FIXTURES / "cim_hardware.json").read_text())


def _fw():
    return json.loads((FIXTURES / "cim_firmware.json").read_text())


def test_gpu_detected():
    items, _ = parse_hardware_data(_hw(), _fw())
    gpus = [i for i in items if i.raw_keys.get("class") == "gpu"]
    assert len(gpus) == 1
    assert "RTX 4070" in gpus[0].raw_name
    assert gpus[0].raw_keys["vendor_id"] == "10DE"


def test_wifi_detected():
    items, _ = parse_hardware_data(_hw(), _fw())
    wifi = [i for i in items if i.raw_keys.get("class") == "wifi"]
    assert len(wifi) >= 1
    assert wifi[0].raw_keys["vendor_id"] == "8086"


def test_firmware_item_present():
    items, _ = parse_hardware_data(_hw(), _fw())
    fw_items = [i for i in items if i.source == "firmware"]
    assert len(fw_items) == 1
    fw = fw_items[0]
    assert fw.raw_keys["secure_boot"] is True
    assert fw.raw_keys["disk_style"] == "GPT"
    assert fw.raw_keys["storage_mode"] == "AHCI"
