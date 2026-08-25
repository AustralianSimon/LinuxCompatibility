"""Tests for the post-install script generator."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.models import ScanItem, ScanResult
from linuxready.report.install_script import generate_install_script


def _result(items: list[ScanItem]) -> ScanResult:
    return ScanResult(
        schema_version="1",
        scan_id="abcd1234-0000-0000-0000-000000000000",
        scanned_at="2026-01-01T00:00:00+00:00",
        db_build="2026-01",
        app_version="0.1.0",
        system={},
        collectors=[],
        items=items,
        score={"value": 100, "hard_blockers": 0, "unknown_count": 0},
    )


def _item(name: str, verdict: str, actions: list[str]) -> ScanItem:
    return ScanItem(source="registry_apps", raw_name=name, raw_keys={},
                    verdict=verdict, actions=actions)


# ── basic output ──────────────────────────────────────────────────────────────

def test_shebang_always_present():
    script = generate_install_script(_result([]))
    assert script.startswith("#!/usr/bin/env bash")


def test_no_packages_produces_comment():
    script = generate_install_script(_result([]))
    assert "No Linux packages" in script


def test_flatpak_command_included():
    item = _item("Firefox", "native",
                 ["[flatpak] flatpak install flathub org.mozilla.firefox"])
    script = generate_install_script(_result([item]))
    assert "flatpak install flathub org.mozilla.firefox" in script


def test_apt_command_included():
    item = _item("VLC", "native",
                 ["[apt] sudo apt install vlc"])
    script = generate_install_script(_result([item]))
    assert "sudo apt install vlc" in script


def test_app_name_appears_as_comment():
    item = _item("Mozilla Firefox", "native",
                 ["[flatpak] flatpak install flathub org.mozilla.firefox"])
    script = generate_install_script(_result([item]))
    assert "# Mozilla Firefox" in script


# ── filtering by verdict ──────────────────────────────────────────────────────

def test_blocked_items_excluded():
    item = _item("Kernel App", "blocked",
                 ["[flatpak] flatpak install flathub com.example.app"])
    script = generate_install_script(_result([item]))
    assert "com.example.app" not in script


def test_unknown_items_excluded():
    item = _item("Mystery App", "unknown",
                 ["[flatpak] flatpak install flathub com.mystery.app"])
    script = generate_install_script(_result([item]))
    assert "com.mystery.app" not in script


def test_replace_items_excluded():
    item = _item("Photoshop", "replace",
                 ["[flatpak] flatpak install flathub org.gimp.GIMP"])
    script = generate_install_script(_result([item]))
    assert "org.gimp.GIMP" not in script


def test_native_items_included():
    item = _item("VLC", "native", ["[apt] sudo apt install vlc"])
    assert "sudo apt install vlc" in generate_install_script(_result([item]))


def test_layer_excellent_items_included():
    item = _item("Some Game", "layer_excellent",
                 ["[flatpak] flatpak install flathub com.example.game"])
    assert "com.example.game" in generate_install_script(_result([item]))


# ── non-package actions are ignored ──────────────────────────────────────────

def test_non_package_actions_not_in_script():
    item = _item("Steam Game", "layer_excellent",
                 ["Enable Proton in Steam › Settings › Compatibility"])
    script = generate_install_script(_result([item]))
    assert "No Linux packages" in script


def test_unknown_ecosystem_ignored():
    item = _item("App", "native", ["[chocolatey] choco install app"])
    script = generate_install_script(_result([item]))
    assert "choco" not in script


# ── flatpak remote setup ──────────────────────────────────────────────────────

def test_flathub_remote_added_when_flatpak_present():
    item = _item("Firefox", "native",
                 ["[flatpak] flatpak install flathub org.mozilla.firefox"])
    script = generate_install_script(_result([item]))
    assert "flathub.flatpakrepo" in script


def test_flathub_remote_not_added_when_only_apt():
    item = _item("VLC", "native", ["[apt] sudo apt install vlc"])
    script = generate_install_script(_result([item]))
    assert "flathub.flatpakrepo" not in script


# ── multiple items and ecosystems ─────────────────────────────────────────────

def test_multiple_items_all_included():
    items = [
        _item("Firefox", "native", ["[flatpak] flatpak install flathub org.mozilla.firefox"]),
        _item("VLC", "native", ["[apt] sudo apt install vlc"]),
    ]
    script = generate_install_script(_result(items))
    assert "org.mozilla.firefox" in script
    assert "sudo apt install vlc" in script


def test_scan_id_in_header():
    script = generate_install_script(_result([]))
    assert "abcd1234" in script
