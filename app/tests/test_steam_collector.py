"""Tests for the Steam collector — no Windows API, runs in any OS."""
import tempfile
from pathlib import Path

import pytest

from linuxready.collectors.steam import (
    parse_app_manifest,
    parse_library_folders,
    collect_steam_items,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_library_folders():
    text = (FIXTURES / "steam_libraryfolders.vdf").read_text()
    paths = parse_library_folders(text)
    assert any("SteamLibrary" in str(p) for p in paths)


def test_parse_app_manifest_dota2():
    text = (FIXTURES / "appmanifest_570.acf").read_text()
    manifest = parse_app_manifest(text)
    assert manifest is not None
    assert manifest["appid"] == 570
    assert manifest["name"] == "Dota 2"
    assert manifest["size_on_disk"] > 0


def test_parse_app_manifest_missing_name():
    acf = '"AppState"\n{\n"appid"\t"999"\n}'
    assert parse_app_manifest(acf) is None


def test_collect_steam_items_with_fixture_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        steamapps = root / "steamapps"
        steamapps.mkdir()

        # Minimal libraryfolders.vdf
        (steamapps / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n"0"\n{\n"path"\t"' + tmp.replace("\\", "\\\\") + '"\n}\n}',
            encoding="utf-8",
        )

        # One game manifest
        (steamapps / "appmanifest_570.acf").write_text(
            (FIXTURES / "appmanifest_570.acf").read_text(), encoding="utf-8"
        )

        items, warnings = collect_steam_items(root)

    assert any(i.raw_keys.get("steam_appid") == 570 for i in items)
    assert all(i.source == "steam" for i in items)
