"""Tests for registry app collector — uses JSON fixture, no winreg."""
import json
from pathlib import Path

from linuxready.collectors.registry_apps import parse_uninstall_entries

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture() -> list[dict]:
    return json.loads((FIXTURES / "registry_dump.json").read_text())


def test_filters_system_components():
    entries = _fixture()
    items, _ = parse_uninstall_entries(entries)
    names = [i.raw_name for i in items]
    assert "Windows Update (KB5040438)" not in names


def test_filters_parent_key_entries():
    entries = _fixture()
    items, _ = parse_uninstall_entries(entries)
    names = [i.raw_name for i in items]
    assert "Hotfix update" not in names


def test_filters_empty_display_name():
    entries = _fixture()
    items, _ = parse_uninstall_entries(entries)
    assert all(i.raw_name for i in items)


def test_captures_known_apps():
    entries = _fixture()
    items, _ = parse_uninstall_entries(entries)
    names = [i.raw_name for i in items]
    assert "Mozilla Firefox" in names
    assert "Adobe Photoshop 2024" in names
    assert "7-Zip 24.08 (x64)" in names


def test_publisher_and_version_captured():
    entries = _fixture()
    items, _ = parse_uninstall_entries(entries)
    firefox = next(i for i in items if i.raw_name == "Mozilla Firefox")
    assert firefox.raw_keys["publisher"] == "Mozilla"
    assert firefox.raw_keys["version"] == "128.0"
