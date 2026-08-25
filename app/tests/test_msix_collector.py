"""Tests for the MSIX / Microsoft Store app collector parser."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
FIXTURE = Path(__file__).parent / "fixtures" / "appx_packages.json"

from linuxready.collectors.msix import parse_appx_packages


def _fixture() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── basic output shape ────────────────────────────────────────────────────────

def test_returns_raw_items_with_msix_source():
    items, _ = parse_appx_packages(_fixture())
    assert all(i.source == "msix" for i in items)

def test_no_warnings_from_clean_input():
    _, warnings = parse_appx_packages(_fixture())
    assert warnings == []

def test_empty_input_returns_empty():
    items, warnings = parse_appx_packages([])
    assert items == []
    assert warnings == []


# ── real apps are kept ────────────────────────────────────────────────────────

def test_vlc_is_included():
    items, _ = parse_appx_packages(_fixture())
    names = [i.raw_name for i in items]
    assert "VLC" in names

def test_gimp_is_included():
    items, _ = parse_appx_packages(_fixture())
    names = [i.raw_name for i in items]
    assert "GIMP" in names

def test_dbeaver_is_included():
    items, _ = parse_appx_packages(_fixture())
    names = [i.raw_name for i in items]
    assert "DBeaver CE" in names

def test_teams_is_included():
    items, _ = parse_appx_packages(_fixture())
    names = [i.raw_name for i in items]
    assert "Microsoft Teams" in names


# ── noise is filtered ─────────────────────────────────────────────────────────

def test_winappruntime_is_filtered():
    items, _ = parse_appx_packages(_fixture())
    names = [i.raw_name for i in items]
    assert "WinAppRuntime.Main.1.4" not in names

def test_ddlm_is_filtered():
    items, _ = parse_appx_packages(_fixture())
    pkg_names = [i.raw_keys.get("package_name", "") for i in items]
    assert not any("DDLM" in (p or "") for p in pkg_names)

def test_null_displayname_is_filtered():
    packages = [{"PackageName": "Microsoft.XboxSpeechToTextOverlay",
                 "DisplayName": None, "Publisher": "Microsoft",
                 "Version": "1.0", "SignatureKind": 3}]
    items, _ = parse_appx_packages(packages)
    assert items == []

def test_ms_resource_displayname_is_filtered():
    packages = [{"PackageName": "Microsoft.VCLibs.140.00",
                 "DisplayName": "ms-resource://Microsoft.VCLibs.140.00/Resources/DisplayName",
                 "Publisher": "Microsoft Corporation",
                 "Version": "14.0.33519.0", "SignatureKind": 3}]
    items, _ = parse_appx_packages(packages)
    assert items == []

def test_fixture_yields_five_apps():
    items, _ = parse_appx_packages(_fixture())
    assert len(items) == 5


# ── raw_keys fields ───────────────────────────────────────────────────────────

def test_publisher_stored_in_raw_keys():
    items, _ = parse_appx_packages(_fixture())
    vlc = next(i for i in items if i.raw_name == "VLC")
    assert vlc.raw_keys["publisher"] == "VideoLAN"

def test_version_stored_in_raw_keys():
    items, _ = parse_appx_packages(_fixture())
    vlc = next(i for i in items if i.raw_name == "VLC")
    assert vlc.raw_keys["version"] == "3.2.1.0"

def test_package_name_stored_in_raw_keys():
    items, _ = parse_appx_packages(_fixture())
    vlc = next(i for i in items if i.raw_name == "VLC")
    assert vlc.raw_keys["package_name"] == "VideoLAN.VLC"
