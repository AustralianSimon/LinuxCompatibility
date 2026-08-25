"""Tests for the hardware collector — uses JSON fixtures, no PowerShell."""
import json
from pathlib import Path

from linuxready.collectors.hardware import _printer_brand_vid, parse_hardware_data

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


def test_printers_detected():
    items, _ = parse_hardware_data(_hw(), _fw())
    printers = [i for i in items if i.raw_keys.get("class") == "printer"]
    assert len(printers) == 2  # Microsoft Print to PDF is virtual and filtered
    names = {i.raw_name for i in printers}
    assert "HP LaserJet Pro M404n" in names
    assert "Canon PIXMA TS9120" in names


def test_virtual_printer_filtered():
    items, _ = parse_hardware_data(_hw(), _fw())
    printers = [i for i in items if i.raw_keys.get("class") == "printer"]
    assert all("Microsoft" not in i.raw_name for i in printers)


def test_printer_known_brand_gets_vendor_id():
    items, _ = parse_hardware_data(_hw(), _fw())
    hp = next(i for i in items if i.raw_keys.get("class") == "printer" and "HP" in i.raw_name)
    assert hp.raw_keys["vendor_id"] == "03F0"


def test_printer_unknown_brand_gets_none_vendor_id():
    hw = {**_hw(), "Printers": [{"Name": "UnknownBrand XL-1000", "PortName": "USB001"}]}
    items, _ = parse_hardware_data(hw, _fw())
    printers = [i for i in items if i.raw_keys.get("class") == "printer"]
    assert len(printers) == 1
    assert printers[0].raw_keys["vendor_id"] is None


def test_printer_brand_vid_known():
    assert _printer_brand_vid("HP LaserJet Pro M404n") == "03F0"
    assert _printer_brand_vid("Brother HL-L2350DW") == "04F9"
    assert _printer_brand_vid("Epson EcoTank ET-2800") == "04B8"


def test_printer_brand_vid_unknown():
    assert _printer_brand_vid("UnknownBrand XL-1000") is None


def test_firmware_item_present():
    items, _ = parse_hardware_data(_hw(), _fw())
    fw_items = [i for i in items if i.source == "firmware"]
    assert len(fw_items) == 1
    fw = fw_items[0]
    assert fw.raw_keys["secure_boot"] is True
    assert fw.raw_keys["disk_style"] == "GPT"
    assert fw.raw_keys["storage_mode"] == "AHCI"
