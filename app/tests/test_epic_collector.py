"""Tests for the Epic Games collector."""
import json
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linuxready.collectors.epic import parse_epic_manifests, read_epic_manifests, EpicCollector

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "epic_manifests.json").read_text(encoding="utf-8")
)


# ── parse_epic_manifests ─────────────────────────────────────────────────────

def test_keeps_game_entries():
    items, warnings = parse_epic_manifests(_FIXTURE)
    names = [i.raw_name for i in items]
    assert "Hades" in names
    assert "Fortnite" in names

def test_filters_non_game_categories():
    items, _ = parse_epic_manifests(_FIXTURE)
    names = [i.raw_name for i in items]
    assert "Epic Games Launcher" not in names

def test_filters_empty_display_name():
    manifests = [{"DisplayName": "", "AppCategories": ["games"]}]
    items, _ = parse_epic_manifests(manifests)
    assert items == []

def test_filters_missing_display_name():
    manifests = [{"CatalogItemId": "xyz", "AppCategories": ["games"]}]
    items, _ = parse_epic_manifests(manifests)
    assert items == []

def test_case_insensitive_games_category():
    items, _ = parse_epic_manifests(_FIXTURE)
    names = [i.raw_name for i in items]
    assert "Hades II" in names

def test_source_is_epic():
    items, _ = parse_epic_manifests(_FIXTURE)
    assert all(i.source == "epic" for i in items)

def test_raw_keys_have_catalog_item_id():
    items, _ = parse_epic_manifests(_FIXTURE)
    hades = next(i for i in items if i.raw_name == "Hades")
    assert hades.raw_keys["catalog_item_id"] == "b7d74be67b614c4694e315e5440e0058"

def test_raw_keys_have_catalog_namespace():
    items, _ = parse_epic_manifests(_FIXTURE)
    hades = next(i for i in items if i.raw_name == "Hades")
    assert hades.raw_keys["catalog_namespace"] == "min"

def test_raw_keys_have_app_name():
    items, _ = parse_epic_manifests(_FIXTURE)
    hades = next(i for i in items if i.raw_name == "Hades")
    assert hades.raw_keys["app_name"] == "CabPatch"

def test_empty_manifests_returns_empty():
    items, warnings = parse_epic_manifests([])
    assert items == []
    assert warnings == []

def test_fixture_produces_expected_count():
    items, _ = parse_epic_manifests(_FIXTURE)
    # Hades, Fortnite, Hades II = 3 games; Epic Launcher + 2 no-name = filtered
    assert len(items) == 3

def test_warnings_always_empty():
    _, warnings = parse_epic_manifests(_FIXTURE)
    assert warnings == []


# ── read_epic_manifests ──────────────────────────────────────────────────────

def test_missing_directory_returns_warning():
    _, warnings = read_epic_manifests(Path("/nonexistent/path/manifests"))
    assert len(warnings) == 1
    assert "not found" in warnings[0]

def test_reads_item_files_from_directory():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_data = {
            "DisplayName": "Test Game",
            "AppCategories": ["games"],
            "CatalogItemId": "testid",
            "CatalogNamespace": "test",
            "AppName": "TestGame",
        }
        (tmp_path / "testgame.item").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )
        manifests, warnings = read_epic_manifests(tmp_path)
        assert len(manifests) == 1
        assert manifests[0]["DisplayName"] == "Test Game"
        assert warnings == []

def test_skips_non_item_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "readme.txt").write_text("not a manifest", encoding="utf-8")
        manifests, warnings = read_epic_manifests(tmp_path)
        assert manifests == []
        assert warnings == []

def test_warns_on_invalid_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "bad.item").write_text("not json {{{", encoding="utf-8")
        manifests, warnings = read_epic_manifests(tmp_path)
        assert manifests == []
        assert len(warnings) == 1


# ── EpicCollector ────────────────────────────────────────────────────────────

def test_available_false_on_non_windows():
    with mock.patch("linuxready.collectors.epic.sys") as mock_sys:
        mock_sys.platform = "linux"
        collector = EpicCollector()
        assert collector.available() is False

def test_available_false_when_dir_missing():
    with mock.patch("linuxready.collectors.epic.sys") as mock_sys, \
         mock.patch("linuxready.collectors.epic._MANIFESTS_DIR") as mock_dir:
        mock_sys.platform = "win32"
        mock_dir.is_dir.return_value = False
        collector = EpicCollector()
        assert collector.available() is False

def test_collector_id():
    assert EpicCollector.id == "epic"
