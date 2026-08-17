"""
Tests for the ProtonDB ingest — all HTTP mocked, no network required.
Response shapes are based on live API responses captured during development.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harvester.sources.protondb import (
    ingest_protondb,
    parse_protondb_summary,
    parse_steam_linux,
)

SCHEMA = (
    Path(__file__).parent.parent.parent
    / "app" / "src" / "linuxready" / "db" / "schema.sql"
)


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """Fresh in-memory DB with the real schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield conn
    conn.close()


# Real response shape for appid 570 (Dota 2), captured 2026-08-15
_DOTA2_PROTONDB = {
    "bestReportedTier": "platinum",
    "confidence": "strong",
    "score": 0.69,
    "tier": "gold",
    "total": 350,
    "trendingTier": "gold",
}

_DOTA2_PLATFORMS = {
    "570": {"success": True, "data": {"platforms": {"windows": True, "mac": True, "linux": True}}}
}

_COD_PROTONDB = {
    "bestReportedTier": "borked",
    "confidence": "good",
    "score": 0.1,
    "tier": "borked",
    "total": 50,
    "trendingTier": "borked",
}

_COD_PLATFORMS = {
    "1938090": {"success": True, "data": {"platforms": {"windows": True, "mac": False, "linux": False}}}
}


# ── parse_protondb_summary ──────────────────────────────────────────────────

def test_parse_gold_tier():
    result = parse_protondb_summary(_DOTA2_PROTONDB)
    assert result == {"proton_tier": "gold", "proton_sample": 350}


def test_parse_pending_returns_none():
    assert parse_protondb_summary({"tier": "pending", "total": 2}) is None


def test_parse_missing_tier_returns_none():
    assert parse_protondb_summary({}) is None


def test_parse_borked_tier():
    result = parse_protondb_summary(_COD_PROTONDB)
    assert result is not None
    assert result["proton_tier"] == "borked"


# ── parse_steam_linux ───────────────────────────────────────────────────────

def test_parse_linux_true():
    assert parse_steam_linux(_DOTA2_PLATFORMS, 570) is True


def test_parse_linux_false():
    assert parse_steam_linux(_COD_PLATFORMS, 1938090) is False


def test_parse_linux_missing_key():
    assert parse_steam_linux({}, 570) is False


# ── ingest_protondb (mocked HTTP) ───────────────────────────────────────────

def _make_response(status: int, json_data=None):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = json_data or {}
    if status >= 400:
        mock.raise_for_status.side_effect = Exception(f"HTTP {status}")
    else:
        mock.raise_for_status.return_value = None
    return mock


def _spy_page(games: list[dict]):
    """Build a SteamSpy page response dict keyed by appid."""
    return {str(g["appid"]): g for g in games}


@patch("harvester.sources.protondb.time.sleep")
@patch("harvester.sources.protondb.requests.Session")
def test_ingest_writes_games_with_protondb_data(MockSession, mock_sleep, db):
    session = MockSession.return_value

    steamspy_page = _spy_page([
        {"appid": 570,     "name": "Dota 2"},
        {"appid": 1938090, "name": "Call of Duty: Modern Warfare III"},
        {"appid": 9999999, "name": "No Reports Game"},
    ])
    # Page 0 returns 3 games; page 1 returns empty → stop
    spy_responses = [
        _make_response(200, steamspy_page),
        _make_response(200, {}),
    ]

    proton_responses = {
        570:     _make_response(200, _DOTA2_PROTONDB),
        1938090: _make_response(200, _COD_PROTONDB),
        9999999: _make_response(404),
    }
    platform_responses = {
        570:     _make_response(200, _DOTA2_PLATFORMS),
        1938090: _make_response(200, _COD_PLATFORMS),
    }

    call_count = {"spy": 0, "proton": 0, "steam": 0}

    def mock_get(url, **kwargs):
        params = kwargs.get("params", {})
        if "steamspy" in url:
            r = spy_responses[call_count["spy"]]
            call_count["spy"] += 1
            return r
        if "protondb" in url:
            appid = int(url.split("/")[-1].replace(".json", ""))
            r = proton_responses[appid]
            if r.status_code == 404:
                r.raise_for_status.side_effect = None  # 404 is handled, not raised
            call_count["proton"] += 1
            return r
        if "steampowered" in url:
            appid = int(params["appids"])
            call_count["steam"] += 1
            return platform_responses[appid]
        raise ValueError(f"Unexpected URL: {url}")

    session.get.side_effect = mock_get

    written = ingest_protondb(db, proton_delay=0, spy_delay=0)

    assert written == 2  # 9999999 (404) is skipped

    rows = db.execute("SELECT steam_appid, name, native_linux, proton_tier FROM game ORDER BY steam_appid").fetchall()
    assert len(rows) == 2

    dota = next(r for r in rows if r[0] == 570)
    assert dota[1] == "Dota 2"
    assert dota[2] == 1          # native Linux
    assert dota[3] == "gold"

    cod = next(r for r in rows if r[0] == 1938090)
    assert cod[2] == 0           # no native Linux
    assert cod[3] == "borked"


@patch("harvester.sources.protondb.time.sleep")
@patch("harvester.sources.protondb.requests.Session")
def test_ingest_limit_stops_early(MockSession, mock_sleep, db):
    session = MockSession.return_value

    page = _spy_page([
        {"appid": 570,     "name": "Dota 2"},
        {"appid": 440,     "name": "Team Fortress 2"},
        {"appid": 730,     "name": "Counter-Strike 2"},
    ])

    def mock_get(url, **kwargs):
        if "steamspy" in url:
            params = kwargs.get("params", {})
            return _make_response(200, page if params.get("page") == 0 else {})
        if "protondb" in url:
            return _make_response(200, _DOTA2_PROTONDB)
        if "steampowered" in url:
            return _make_response(200, _DOTA2_PLATFORMS)
        raise ValueError(url)

    session.get.side_effect = mock_get

    written = ingest_protondb(db, limit=1, proton_delay=0, spy_delay=0)
    assert written == 1


@patch("harvester.sources.protondb.time.sleep")
@patch("harvester.sources.protondb.requests.Session")
def test_ingest_does_not_overwrite_anticheat(MockSession, mock_sleep, db):
    """anticheat column must survive a ProtonDB upsert (set by _ingest_anticheat later)."""
    session = MockSession.return_value

    # Pre-seed a game row with anticheat=kernel_blocked
    db.execute(
        "INSERT INTO game (steam_appid, name, native_linux, anticheat) VALUES (570, 'Dota 2', 0, 'kernel_blocked')"
    )
    db.commit()

    page = _spy_page([{"appid": 570, "name": "Dota 2"}])

    def mock_get(url, **kwargs):
        if "steamspy" in url:
            params = kwargs.get("params", {})
            return _make_response(200, page if params.get("page") == 0 else {})
        if "protondb" in url:
            return _make_response(200, _DOTA2_PROTONDB)
        if "steampowered" in url:
            return _make_response(200, _DOTA2_PLATFORMS)
        raise ValueError(url)

    session.get.side_effect = mock_get

    ingest_protondb(db, proton_delay=0, spy_delay=0)

    row = db.execute("SELECT anticheat FROM game WHERE steam_appid = 570").fetchone()
    assert row[0] == "kernel_blocked"  # must not be clobbered
