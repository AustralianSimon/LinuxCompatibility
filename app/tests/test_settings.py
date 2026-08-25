"""Tests for settings persistence and scan persistence."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.settings import Settings, load_settings, save_settings
from linuxready.scan_persist import list_scans, save_scan
from linuxready.models import ScanResult


# ── settings ─────────────────────────────────────────────────────────────────

def test_load_missing_returns_defaults(tmp_path):
    s = load_settings(tmp_path / "nope.json")
    assert s.theme == "dark"
    assert s.portable_scan is False


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(theme="light", portable_scan=True)
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.theme == "light"
    assert loaded.portable_scan is True


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "settings.json"
    save_settings(Settings(), path)
    assert path.exists()


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json {{{", encoding="utf-8")
    s = load_settings(path)
    assert s.theme == "dark"


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "auto", "future_key": 42}), encoding="utf-8")
    s = load_settings(path)
    assert s.theme == "auto"


# ── scan persistence ──────────────────────────────────────────────────────────

def _fake_result(scan_id: str = "abcd1234-test") -> ScanResult:
    return ScanResult(
        schema_version="1",
        scan_id=scan_id,
        scanned_at="2026-08-14T10:00:00+00:00",
        db_build="2026-08",
        app_version="0.1.0",
        system={},
        collectors=[],
        items=[],
        score={"value": 85, "hard_blockers": 0, "unknown_count": 2},
    )


def test_save_scan_creates_file(tmp_path):
    path = save_scan(_fake_result(), scans_dir=tmp_path)
    assert path.exists()


def test_save_scan_filename_contains_scan_id(tmp_path):
    result = _fake_result("deadbeef-0000-0000-0000-000000000000")
    path = save_scan(result, scans_dir=tmp_path)
    assert "deadbeef" in path.name


def test_save_scan_is_valid_json(tmp_path):
    path = save_scan(_fake_result(), scans_dir=tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1"
    assert data["score"]["value"] == 85


def test_list_scans_empty_dir(tmp_path):
    assert list_scans(tmp_path) == []


def test_list_scans_missing_dir(tmp_path):
    assert list_scans(tmp_path / "nonexistent") == []


def test_list_scans_returns_newest_first(tmp_path):
    r1 = _fake_result("aaaa")
    r1 = ScanResult(**{**r1.__dict__, "scanned_at": "2026-01-01T00:00:00+00:00"})
    r2 = _fake_result("bbbb")
    r2 = ScanResult(**{**r2.__dict__, "scanned_at": "2026-06-01T00:00:00+00:00"})
    save_scan(r1, scans_dir=tmp_path)
    save_scan(r2, scans_dir=tmp_path)
    scans = list_scans(tmp_path)
    assert len(scans) == 2
    assert "bbbb" in scans[0].name   # newer first


def test_save_scan_prunes_old_files(tmp_path):
    import linuxready.scan_persist as sp
    old_max = sp._MAX_SAVED
    sp._MAX_SAVED = 3
    try:
        for i in range(5):
            r = _fake_result(f"id{i:04d}-0000-0000-0000-000000000000")
            r = ScanResult(**{**r.__dict__,
                              "scanned_at": f"2026-0{i+1}-01T00:00:00+00:00"})
            save_scan(r, scans_dir=tmp_path)
        assert len(list(tmp_path.glob("scan_*.json"))) == 3
    finally:
        sp._MAX_SAVED = old_max
