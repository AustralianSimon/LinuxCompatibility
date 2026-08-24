"""Tests for the GOG Galaxy collector."""
import json
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linuxready.collectors.gog import parse_gog_entries, GogCollector

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "gog_registry.json").read_text(encoding="utf-8")
)


# ── parse_gog_entries ────────────────────────────────────────────────────────

def test_keeps_entries_with_game_name():
    items, _ = parse_gog_entries(_FIXTURE)
    names = [i.raw_name for i in items]
    assert "The Witcher 3: Wild Hunt" in names
    assert "Cyberpunk 2077" in names
    assert "Baldur's Gate 3" in names

def test_filters_empty_game_name():
    items, _ = parse_gog_entries(_FIXTURE)
    names = [i.raw_name for i in items]
    assert "" not in names

def test_filters_missing_game_name_key():
    items, _ = parse_gog_entries(_FIXTURE)
    # Entry with no GAMENAME key must be excluded
    assert len(items) == 3

def test_source_is_gog():
    items, _ = parse_gog_entries(_FIXTURE)
    assert all(i.source == "gog" for i in items)

def test_raw_keys_have_product_id():
    items, _ = parse_gog_entries(_FIXTURE)
    witcher = next(i for i in items if "Witcher" in i.raw_name)
    assert witcher.raw_keys["gog_product_id"] == "1207664643"

def test_raw_keys_have_publisher():
    items, _ = parse_gog_entries(_FIXTURE)
    witcher = next(i for i in items if "Witcher" in i.raw_name)
    assert witcher.raw_keys["publisher"] == "CD PROJEKT RED"

def test_publisher_none_when_not_present():
    entries = [{"GAMENAME": "Solo Game", "productid": "123"}]
    items, _ = parse_gog_entries(entries)
    assert items[0].raw_keys["publisher"] is None

def test_empty_entries_returns_empty():
    items, warnings = parse_gog_entries([])
    assert items == []
    assert warnings == []

def test_warnings_always_empty():
    _, warnings = parse_gog_entries(_FIXTURE)
    assert warnings == []

def test_fixture_produces_expected_count():
    items, _ = parse_gog_entries(_FIXTURE)
    assert len(items) == 3


# ── GogCollector ─────────────────────────────────────────────────────────────

def test_available_false_on_non_windows():
    with mock.patch("linuxready.collectors.gog.sys") as mock_sys:
        mock_sys.platform = "linux"
        collector = GogCollector()
        assert collector.available() is False

def test_available_false_when_key_missing():
    # available() does `import winreg` internally — patch sys.modules to simulate missing key
    with mock.patch("linuxready.collectors.gog.sys") as mock_sys:
        mock_sys.platform = "win32"
        import winreg
        with mock.patch.object(winreg, "OpenKey", side_effect=FileNotFoundError):
            collector = GogCollector()
            assert collector.available() is False

def test_collector_id():
    assert GogCollector.id == "gog"
