"""
Tests for the ProtonDB ingest — all HTTP mocked, no network required.
Response shapes are based on live API responses captured during development.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import json

import requests

from harvester.sources.protondb import (
    _fetch_steamspy_page,
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


# ── sync state: skip-if-fresh ────────────────────────────────────────────────

def test_skips_if_recent_sync_completed(db):
    """Return None without touching the network when last sync was recent."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    db.execute("INSERT INTO meta VALUES ('protondb_sync_completed_at', ?)", (now,))
    db.commit()

    result = ingest_protondb(db, max_age_hours=24.0)

    assert result is None


def test_does_not_skip_if_sync_too_old(db):
    """Re-runs when last completed sync is older than max_age_hours."""
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).replace(microsecond=0).isoformat()
    db.execute("INSERT INTO meta VALUES ('protondb_sync_completed_at', ?)", (old,))
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

    with patch("harvester.sources.protondb.requests.Session") as MockSession, \
         patch("harvester.sources.protondb.time.sleep"):
        MockSession.return_value.get.side_effect = mock_get
        result = ingest_protondb(db, max_age_hours=24.0, proton_delay=0, spy_delay=0)

    assert result == 1  # ran and wrote 1 game


def test_does_not_skip_when_max_age_is_zero(db):
    """max_age_hours=0 disables freshness check entirely."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    db.execute("INSERT INTO meta VALUES ('protondb_sync_completed_at', ?)", (now,))
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

    with patch("harvester.sources.protondb.requests.Session") as MockSession, \
         patch("harvester.sources.protondb.time.sleep"):
        MockSession.return_value.get.side_effect = mock_get
        result = ingest_protondb(db, max_age_hours=0, proton_delay=0, spy_delay=0)

    assert result == 1  # ran despite recent completion


# ── sync state: marks complete / written to meta ─────────────────────────────

@patch("harvester.sources.protondb.time.sleep")
@patch("harvester.sources.protondb.requests.Session")
def test_marks_sync_complete_after_full_run(MockSession, mock_sleep, db):
    """completed_at is set and started_at / page are cleared after a full run."""
    session = MockSession.return_value

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

    def _meta(key):
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    assert _meta("protondb_sync_completed_at") is not None  # marked complete
    assert _meta("protondb_sync_started_at") is None        # cleaned up
    assert _meta("protondb_sync_page") is None              # cleaned up


def test_no_meta_written_when_limit_set(db):
    """limit= runs leave no sync state in meta (dev/test isolation)."""
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

    with patch("harvester.sources.protondb.requests.Session") as MockSession, \
         patch("harvester.sources.protondb.time.sleep"):
        MockSession.return_value.get.side_effect = mock_get
        ingest_protondb(db, limit=1, proton_delay=0, spy_delay=0)

    rows = db.execute("SELECT key FROM meta").fetchall()
    assert rows == []  # no sync state pollutes meta


# ── sync state: page-level resume ────────────────────────────────────────────

@patch("harvester.sources.protondb.time.sleep")
@patch("harvester.sources.protondb.requests.Session")
def test_resume_skips_completed_pages(MockSession, mock_sleep, db):
    """When protondb_sync_page=0 is in meta, page 0 is never requested."""
    session = MockSession.return_value

    # Seed meta to look like page 0 was already completed in a prior interrupted run
    db.execute("INSERT INTO meta VALUES ('protondb_sync_started_at', '2020-01-01T00:00:00+00:00')")
    db.execute("INSERT INTO meta VALUES ('protondb_sync_page', '0')")
    db.commit()

    # Only page 1 games — page 0 must not be fetched
    page1 = _spy_page([{"appid": 440, "name": "Team Fortress 2"}])
    pages_requested = []

    def mock_get(url, **kwargs):
        if "steamspy" in url:
            p = kwargs.get("params", {}).get("page", 0)
            pages_requested.append(p)
            return _make_response(200, page1 if p == 1 else {})
        if "protondb" in url:
            return _make_response(200, _DOTA2_PROTONDB)
        if "steampowered" in url:
            return _make_response(200, _DOTA2_PLATFORMS)
        raise ValueError(url)

    session.get.side_effect = mock_get
    written = ingest_protondb(db, proton_delay=0, spy_delay=0)

    assert 0 not in pages_requested, "page 0 should have been skipped by resume"
    assert written == 1
    # Game from page 1 is in the DB
    row = db.execute("SELECT name FROM game WHERE steam_appid = 440").fetchone()
    assert row is not None


# ── _fetch_steamspy_page retry logic ─────────────────────────────────────────

def _session_returning(*responses):
    """Build a mock Session whose .get() returns responses in sequence."""
    session = MagicMock()
    session.get.side_effect = list(responses)
    return session


def _resp_ok(data: dict):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = data
    return r


def _resp_empty_body():
    """Simulates SteamSpy returning a blank body (its 'no more pages' signal).
    content is non-empty (e.g. b'\\r\\n') but text decodes to whitespace-only."""
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.content = b"\r\n"
    r.text = "\r\n"
    return r


def _resp_garbage_body():
    """Simulates a non-empty but unparseable body (rate-limit HTML, etc.)."""
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.text = "<html>Rate limited</html>"
    r.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    return r


def _resp_connection_failed():
    """Simulates SteamSpy's 'Connection failed: Too many connections' MySQL overload."""
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.text = "Connection failed: Too many connections"
    r.json.side_effect = json.JSONDecodeError("Expecting value", "C", 0)
    return r


def _resp_http_error(code: int):
    exc = requests.HTTPError(response=MagicMock(status_code=code))
    r = MagicMock()
    r.raise_for_status.side_effect = exc
    return r


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_empty_body_returns_none_immediately(mock_sleep):
    """Empty HTTP body is SteamSpy's end-of-data signal — stop without retrying."""
    session = _session_returning(_resp_empty_body())

    result = _fetch_steamspy_page(session, page=87, max_retries=3)

    assert result is None
    assert session.get.call_count == 1
    mock_sleep.assert_not_called()


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_retries_on_garbage_body(mock_sleep):
    """Non-empty but unparseable body (rate-limit HTML) triggers a retry."""
    data = {"1": {"appid": 1, "name": "Game"}}
    session = _session_returning(_resp_garbage_body(), _resp_ok(data))

    result = _fetch_steamspy_page(session, page=87, max_retries=3)

    assert result == data
    assert session.get.call_count == 2
    mock_sleep.assert_called_once()


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_retries_on_connection_error(mock_sleep):
    data = {"1": {"appid": 1, "name": "Game"}}
    session = MagicMock()
    session.get.side_effect = [requests.ConnectionError("reset"), _resp_ok(data)]

    result = _fetch_steamspy_page(session, page=5, max_retries=3)

    assert result == data
    assert session.get.call_count == 2


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_retries_on_5xx(mock_sleep):
    data = {"1": {"appid": 1, "name": "Game"}}
    session = _session_returning(_resp_http_error(503), _resp_ok(data))

    result = _fetch_steamspy_page(session, page=10, max_retries=3)

    assert result == data
    assert session.get.call_count == 2


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_raises_after_all_retries_exhausted(mock_sleep):
    session = _session_returning(
        _resp_garbage_body(), _resp_garbage_body(), _resp_garbage_body(), _resp_garbage_body()
    )

    with pytest.raises(RuntimeError, match="retries exhausted"):
        _fetch_steamspy_page(session, page=87, max_retries=3)

    assert session.get.call_count == 4  # 1 initial + 3 retries


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_connection_failed_returns_none_immediately(mock_sleep):
    """'Connection failed: Too many connections' is SteamSpy's end-of-data signal — no retry."""
    session = _session_returning(_resp_connection_failed())

    result = _fetch_steamspy_page(session, page=87, max_retries=3)

    assert result is None
    assert session.get.call_count == 1  # no retries
    mock_sleep.assert_not_called()


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_raises_immediately_on_4xx(mock_sleep):
    session = _session_returning(_resp_http_error(403))

    with pytest.raises(requests.HTTPError):
        _fetch_steamspy_page(session, page=1, max_retries=3)

    assert session.get.call_count == 1  # no retry on 4xx


@patch("harvester.sources.protondb.time.sleep")
def test_steamspy_page_returns_none_on_empty_data(mock_sleep):
    session = _session_returning(_resp_ok({}))
    result = _fetch_steamspy_page(session, page=999, max_retries=3)
    assert result is None
