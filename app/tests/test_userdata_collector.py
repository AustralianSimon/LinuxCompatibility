"""Tests for the userdata / migration sizing collector."""
import os
from pathlib import Path

import pytest

from linuxready.collectors.userdata import _dir_size_gb, _pst_size_gb, collect_migration


# ── _dir_size_gb ─────────────────────────────────────────────────────────────

def test_dir_size_empty(tmp_path):
    assert _dir_size_gb(tmp_path) == 0.0


def test_dir_size_single_file(tmp_path):
    (tmp_path / "file.txt").write_bytes(b"x" * 1024 * 1024)  # 1 MB → 0.001 GB (3 dp)
    size = _dir_size_gb(tmp_path)
    assert size >= 0.001


def test_dir_size_nested(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.bin").write_bytes(b"0" * 1024 * 1024)  # 1 MB
    (sub / "b.bin").write_bytes(b"0" * 1024 * 1024)       # 1 MB
    size = _dir_size_gb(tmp_path)
    assert size >= 0.002


def test_dir_size_missing_path(tmp_path):
    assert _dir_size_gb(tmp_path / "nonexistent") == 0.0


# ── _pst_size_gb ─────────────────────────────────────────────────────────────

def test_pst_size_finds_pst_and_ost(tmp_path):
    (tmp_path / "archive.pst").write_bytes(b"0" * 1024 * 1024)   # 1 MB
    (tmp_path / "cache.ost").write_bytes(b"0" * 2 * 1024 * 1024) # 2 MB → total 3 MB = 0.003 GB
    (tmp_path / "readme.txt").write_bytes(b"ignored")
    size = _pst_size_gb(tmp_path)
    assert size >= 0.003


def test_pst_size_empty(tmp_path):
    assert _pst_size_gb(tmp_path) == 0.0


# ── collect_migration ─────────────────────────────────────────────────────────

def _fake_env(tmp_path: Path) -> dict:
    """Build a fake env pointing to a tmp_path structure."""
    profile = tmp_path / "Users" / "testuser"
    localappdata = tmp_path / "LocalAppData"
    appdata = tmp_path / "AppData" / "Roaming"

    # User folders
    (profile / "Documents").mkdir(parents=True)
    (profile / "Documents" / "notes.txt").write_bytes(b"hello")
    (profile / "Downloads").mkdir(parents=True)

    # Firefox profile (exists)
    firefox = appdata / "Mozilla" / "Firefox" / "Profiles"
    firefox.mkdir(parents=True)
    (firefox / "profile.json").write_bytes(b"{}")

    return {
        "USERPROFILE": str(profile),
        "LOCALAPPDATA": str(localappdata),
        "APPDATA": str(appdata),
    }


def test_collect_migration_finds_documents(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    docs = next(i for i in items if i.name == "Documents")
    assert docs.found is True
    assert docs.category == "documents"
    assert docs.size_gb >= 0.0


def test_collect_migration_missing_folder_not_found(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    # Downloads dir was created but is empty — found=True, size=0
    dl = next(i for i in items if i.name == "Downloads")
    assert dl.found is True
    assert dl.size_gb == 0.0


def test_collect_migration_missing_browser_not_found(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    chrome = next(i for i in items if i.name == "Chrome profile")
    assert chrome.found is False
    assert chrome.size_gb == 0.0


def test_collect_migration_firefox_found(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    ff = next(i for i in items if i.name == "Firefox profile")
    assert ff.found is True
    assert ff.category == "browser"


def test_collect_migration_all_categories_present(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    categories = {i.category for i in items}
    assert "documents" in categories
    assert "browser" in categories
    assert "mail" in categories


def test_collect_migration_empty_env():
    items = collect_migration({})
    # All paths will be relative to empty strings — nothing found
    assert all(not i.found for i in items)


def test_collect_migration_notes_not_empty(tmp_path):
    items = collect_migration(_fake_env(tmp_path))
    assert all(i.note for i in items)
