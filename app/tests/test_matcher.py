"""Tests for normalize and the resolver cascade — uses seed DB."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.matcher.normalize import normalize
from linuxready.matcher.resolver import resolve
from linuxready.models import RawItem

SEED_DB = ROOT / "src" / "linuxready" / "db" / "compat.db"


def _conn():
    if not SEED_DB.exists():
        pytest.skip("seed compat.db not found — run: python -m linuxready.db.seed")
    return sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True)


# ── normalize ────────────────────────────────────────────────────────────────

def test_normalize_strips_version():
    assert normalize("Adobe Photoshop 2024") == "adobe photoshop"


def test_normalize_strips_arch():
    assert normalize("7-Zip 24.08 (x64)") == "7 zip 24 08"


def test_normalize_strips_symbols():
    assert normalize("VLC™ media player") == "vlc media player"


def test_normalize_collapses_whitespace():
    assert normalize("  Firefox   ") == "firefox"


# ── resolver ─────────────────────────────────────────────────────────────────

def test_tier1_steam_appid():
    conn = _conn()
    item = RawItem(source="steam", raw_name="Dota 2", raw_keys={"steam_appid": 570})
    result = resolve(item, conn)
    conn.close()
    assert result.matched_id == "steam:570"
    assert result.match_tier == 1
    assert result.match_confidence == "exact"


def test_tier2_curated_alias():
    conn = _conn()
    item = RawItem(source="registry_apps", raw_name="firefox",
                   raw_keys={"publisher": None})
    result = resolve(item, conn)
    conn.close()
    assert result.matched_id == "mozilla.firefox"
    assert result.match_tier == 2


def test_tier4_unique_name():
    conn = _conn()
    item = RawItem(source="registry_apps", raw_name="VLC media player",
                   raw_keys={"publisher": "VideoLAN"})
    result = resolve(item, conn)
    conn.close()
    assert result.matched_id == "vlc.vlc"


def test_unknown_app_returns_none():
    conn = _conn()
    item = RawItem(source="registry_apps", raw_name="zzz_totally_unknown_app_xyz",
                   raw_keys={"publisher": None})
    result = resolve(item, conn)
    conn.close()
    assert result.matched_id is None
    assert result.match_confidence == "unknown"
