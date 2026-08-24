"""Tests for verdict rules and scoring — uses seed DB."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.models import ScanItem
from linuxready.verdict.rules import assign_verdict
from linuxready.verdict.score import compute_score

SEED_DB = ROOT / "src" / "linuxready" / "db" / "compat.db"


def _conn():
    if not SEED_DB.exists():
        pytest.skip("seed compat.db not found — run: python -m linuxready.db.seed")
    return sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True)


def _game(appid: int, name: str = "Test") -> ScanItem:
    return ScanItem(source="steam", raw_name=name,
                    raw_keys={"steam_appid": appid},
                    matched_id=str(appid), match_tier=1, match_confidence="exact")


def _app(app_id: str, name: str = "Test") -> ScanItem:
    return ScanItem(source="registry_apps", raw_name=name,
                    raw_keys={}, matched_id=app_id, match_tier=2, match_confidence="exact")


# ── game verdicts ─────────────────────────────────────────────────────────

def test_dota2_is_native():
    conn = _conn()
    item = assign_verdict(_game(570, "Dota 2"), conn)
    conn.close()
    assert item.verdict == "native"
    assert not item.is_blocker


def test_cyberpunk_is_layer_excellent():
    conn = _conn()
    item = assign_verdict(_game(1091500, "Cyberpunk 2077"), conn)
    conn.close()
    assert item.verdict == "layer_excellent"


def test_kernel_anticheat_is_blocker():
    conn = _conn()
    item = assign_verdict(_game(1938090, "CoD MW3"), conn)
    conn.close()
    assert item.verdict == "blocked"
    assert item.is_blocker


# ── app verdicts ─────────────────────────────────────────────────────────

def test_firefox_is_native():
    conn = _conn()
    item = assign_verdict(_app("mozilla.firefox", "Firefox"), conn)
    conn.close()
    assert item.verdict == "native"


def test_photoshop_is_replace():
    conn = _conn()
    item = assign_verdict(_app("adobe.photoshop", "Adobe Photoshop"), conn)
    conn.close()
    assert item.verdict == "replace"
    assert any("Alternative" in e for e in item.evidence)


# ── firmware verdicts ──────────────────────────────────────────────────

def test_rst_raid_is_blocker():
    conn = _conn()
    item = ScanItem(source="firmware", raw_name="Firmware",
                    raw_keys={"storage_mode": "RST/RAID", "bitlocker": "Off",
                               "disk_style": "GPT", "free_gb": 200.0})
    assign_verdict(item, conn)
    conn.close()
    assert item.verdict == "blocked"
    assert item.is_blocker


def test_low_disk_space_is_blocker():
    conn = _conn()
    item = ScanItem(source="firmware", raw_name="Firmware",
                    raw_keys={"storage_mode": "AHCI", "bitlocker": "Off",
                               "disk_style": "GPT", "free_gb": 10.0})
    assign_verdict(item, conn)
    conn.close()
    assert item.is_blocker


# ── score ─────────────────────────────────────────────────────────────────

def test_score_all_native():
    items = [
        ScanItem(source="steam", raw_name="G1", raw_keys={}, verdict="native"),
        ScanItem(source="registry_apps", raw_name="A1", raw_keys={}, verdict="native"),
    ]
    s = compute_score(items)
    assert s["value"] == 100
    assert s["hard_blockers"] == 0


def test_score_drops_with_blockers():
    items = [
        ScanItem(source="steam", raw_name="G1", raw_keys={}, verdict="blocked", is_blocker=True),
        ScanItem(source="registry_apps", raw_name="A1", raw_keys={}, verdict="native"),
    ]
    s = compute_score(items)
    assert s["hard_blockers"] == 1
    assert s["value"] < 100
