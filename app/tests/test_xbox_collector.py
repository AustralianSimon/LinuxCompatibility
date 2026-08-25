"""Tests for the Xbox / Game Pass collector."""
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linuxready.collectors.xbox import (
    XboxCollector,
    collect_xbox_items,
    parse_appx_manifest,
    parse_microsoft_game_config,
    read_game_dir,
)

# ── MicrosoftGame.config parser ───────────────────────────────────────────────

_MSGC_WITH_NS = """\
<?xml version="1.0" encoding="utf-8"?>
<Game configVersion="0"
      xmlns="http://schemas.microsoft.com/Gaming/2018/06/MicrosoftGameConfig">
  <Identity Name="Microsoft.HaloInfinite_8wekyb3d8bbwe"
            Publisher="CN=Microsoft Corporation" Version="1.0.0.0"/>
  <DisplayName>Halo Infinite</DisplayName>
  <Description>Master Chief returns.</Description>
</Game>
"""

_MSGC_NO_NS = """\
<?xml version="1.0" encoding="utf-8"?>
<Game configVersion="0">
  <Identity Name="Forza.ForzaHorizon5PC_8wekyb3d8bbwe" Publisher="CN=Microsoft"/>
  <DisplayName>Forza Horizon 5</DisplayName>
</Game>
"""

_MSGC_MS_RESOURCE = """\
<?xml version="1.0" encoding="utf-8"?>
<Game xmlns="http://schemas.microsoft.com/Gaming/2018/06/MicrosoftGameConfig">
  <Identity Name="SomeGame_xyz"/>
  <DisplayName>ms-resource:AppName</DisplayName>
</Game>
"""

_MSGC_NO_DISPLAY_NAME = """\
<?xml version="1.0" encoding="utf-8"?>
<Game xmlns="http://schemas.microsoft.com/Gaming/2018/06/MicrosoftGameConfig">
  <Identity Name="NoName_xyz"/>
</Game>
"""


def test_parse_msgc_with_namespace():
    result = parse_microsoft_game_config(_MSGC_WITH_NS)
    assert result is not None
    assert result["name"] == "Halo Infinite"
    assert result["package_name"] == "Microsoft.HaloInfinite_8wekyb3d8bbwe"


def test_parse_msgc_without_namespace():
    result = parse_microsoft_game_config(_MSGC_NO_NS)
    assert result is not None
    assert result["name"] == "Forza Horizon 5"


def test_parse_msgc_rejects_ms_resource():
    assert parse_microsoft_game_config(_MSGC_MS_RESOURCE) is None


def test_parse_msgc_rejects_missing_display_name():
    assert parse_microsoft_game_config(_MSGC_NO_DISPLAY_NAME) is None


def test_parse_msgc_rejects_invalid_xml():
    assert parse_microsoft_game_config("not xml {{{") is None


# ── AppxManifest.xml parser ───────────────────────────────────────────────────

_APPX_WITH_NS = """\
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
  <Identity Name="Microsoft.ShadowOfTheTombRaider_8wekyb3d8bbwe" Version="1.0.0.0"/>
  <Properties>
    <DisplayName>Shadow of the Tomb Raider</DisplayName>
    <PublisherDisplayName>Square Enix</PublisherDisplayName>
  </Properties>
</Package>
"""

_APPX_MS_RESOURCE = """\
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
  <Identity Name="SomeGame_xyz"/>
  <Properties>
    <DisplayName>ms-resource:AppName</DisplayName>
  </Properties>
</Package>
"""

_APPX_NO_NS = """\
<?xml version="1.0" encoding="utf-8"?>
<Package>
  <Identity Name="FallbackGame_abc"/>
  <Properties>
    <DisplayName>Fallback Game</DisplayName>
  </Properties>
</Package>
"""


def test_parse_appx_with_namespace():
    result = parse_appx_manifest(_APPX_WITH_NS)
    assert result is not None
    assert result["name"] == "Shadow of the Tomb Raider"
    assert result["package_name"] == "Microsoft.ShadowOfTheTombRaider_8wekyb3d8bbwe"


def test_parse_appx_without_namespace():
    result = parse_appx_manifest(_APPX_NO_NS)
    assert result is not None
    assert result["name"] == "Fallback Game"


def test_parse_appx_rejects_ms_resource():
    assert parse_appx_manifest(_APPX_MS_RESOURCE) is None


def test_parse_appx_rejects_invalid_xml():
    assert parse_appx_manifest("<<<bad>>>") is None


# ── read_game_dir ─────────────────────────────────────────────────────────────

def test_read_prefers_msgc_over_appxmanifest(tmp_path):
    content = tmp_path / "Content"
    content.mkdir()
    (content / "MicrosoftGame.config").write_text(_MSGC_WITH_NS, encoding="utf-8")
    (content / "AppxManifest.xml").write_text(_APPX_WITH_NS, encoding="utf-8")
    result = read_game_dir(tmp_path)
    assert result is not None
    assert result["name"] == "Halo Infinite"


def test_read_falls_back_to_appxmanifest(tmp_path):
    content = tmp_path / "Content"
    content.mkdir()
    (content / "AppxManifest.xml").write_text(_APPX_WITH_NS, encoding="utf-8")
    result = read_game_dir(tmp_path)
    assert result is not None
    assert result["name"] == "Shadow of the Tomb Raider"


def test_read_falls_back_to_root_dir(tmp_path):
    """Config at game_dir root (no Content/ subdir) is still found."""
    (tmp_path / "MicrosoftGame.config").write_text(_MSGC_NO_NS, encoding="utf-8")
    result = read_game_dir(tmp_path)
    assert result is not None
    assert result["name"] == "Forza Horizon 5"


def test_read_returns_none_when_no_config(tmp_path):
    (tmp_path / "Content").mkdir()
    assert read_game_dir(tmp_path) is None


def test_read_returns_none_for_ms_resource_config(tmp_path):
    content = tmp_path / "Content"
    content.mkdir()
    (content / "MicrosoftGame.config").write_text(_MSGC_MS_RESOURCE, encoding="utf-8")
    assert read_game_dir(tmp_path) is None


# ── collect_xbox_items ────────────────────────────────────────────────────────

def test_collect_missing_dir_returns_warning(tmp_path):
    items, warnings = collect_xbox_items(tmp_path / "nonexistent")
    assert items == []
    assert len(warnings) == 1
    assert "not found" in warnings[0]


def test_collect_finds_games_in_subdirs(tmp_path):
    for name, xml in [("Halo Infinite", _MSGC_WITH_NS), ("Shadow", _APPX_WITH_NS)]:
        game_dir = tmp_path / name / "Content"
        game_dir.mkdir(parents=True)
        config = "MicrosoftGame.config" if "Halo" in name else "AppxManifest.xml"
        (game_dir / config).write_text(xml, encoding="utf-8")

    items, warnings = collect_xbox_items(tmp_path)
    names = {i.raw_name for i in items}
    assert "Halo Infinite" in names
    assert "Shadow of the Tomb Raider" in names
    assert warnings == []


def test_collect_skips_unresolvable_configs(tmp_path):
    game_dir = tmp_path / "MysteryGame" / "Content"
    game_dir.mkdir(parents=True)
    (game_dir / "MicrosoftGame.config").write_text(_MSGC_MS_RESOURCE, encoding="utf-8")

    items, warnings = collect_xbox_items(tmp_path)
    assert items == []
    assert warnings == []


def test_collect_skips_files_not_dirs(tmp_path):
    (tmp_path / "somefile.txt").write_text("junk", encoding="utf-8")
    game_dir = tmp_path / "Real Game" / "Content"
    game_dir.mkdir(parents=True)
    (game_dir / "MicrosoftGame.config").write_text(_MSGC_NO_NS, encoding="utf-8")

    items, _ = collect_xbox_items(tmp_path)
    assert len(items) == 1


def test_collect_source_is_xbox(tmp_path):
    game_dir = tmp_path / "FH5" / "Content"
    game_dir.mkdir(parents=True)
    (game_dir / "MicrosoftGame.config").write_text(_MSGC_NO_NS, encoding="utf-8")

    items, _ = collect_xbox_items(tmp_path)
    assert len(items) == 1
    assert items[0].source == "xbox"


def test_collect_raw_keys_include_package_name(tmp_path):
    game_dir = tmp_path / "Halo" / "Content"
    game_dir.mkdir(parents=True)
    (game_dir / "MicrosoftGame.config").write_text(_MSGC_WITH_NS, encoding="utf-8")

    items, _ = collect_xbox_items(tmp_path)
    assert items[0].raw_keys["package_name"] == "Microsoft.HaloInfinite_8wekyb3d8bbwe"


# ── XboxCollector ─────────────────────────────────────────────────────────────

def test_collector_id():
    assert XboxCollector.id == "xbox"


def test_available_false_on_non_windows():
    with mock.patch("linuxready.collectors.xbox.sys") as mock_sys:
        mock_sys.platform = "linux"
        assert XboxCollector().available() is False


def test_available_false_when_dir_missing():
    with mock.patch("linuxready.collectors.xbox.sys") as mock_sys, \
         mock.patch("linuxready.collectors.xbox._DEFAULT_GAMES_DIR") as mock_dir:
        mock_sys.platform = "win32"
        mock_dir.is_dir.return_value = False
        assert XboxCollector().available() is False
