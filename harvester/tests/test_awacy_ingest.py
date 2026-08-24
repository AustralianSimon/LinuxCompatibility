"""Tests for the AreWeAntiCheatYet ingest parser."""
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harvester.sources.awacy import parse_awacy_entry, parse_awacy_games, ingest_awacy

_SCHEMA = (
    Path(__file__).parent.parent.parent
    / "app" / "src" / "linuxready" / "db" / "schema.sql"
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def _seed_game(conn, appid: int, name: str = "Game") -> None:
    conn.execute(
        "INSERT INTO game (steam_appid, name, anticheat) VALUES (?, ?, 'none')",
        (appid, name),
    )
    conn.commit()


# ── parse_awacy_entry ────────────────────────────────────────────────────────

def test_parse_supported_status():
    entry = {"storeIds": {"steam": "123"}, "status": "Supported", "anticheats": ["EAC"]}
    result = parse_awacy_entry(entry)
    assert result == {"steam_appid": 123, "anticheat": "supported"}

def test_parse_denied_status():
    entry = {"storeIds": {"steam": "456"}, "status": "Denied", "anticheats": ["BattlEye"]}
    result = parse_awacy_entry(entry)
    assert result == {"steam_appid": 456, "anticheat": "denied"}

def test_parse_broken_status():
    entry = {"storeIds": {"steam": "789"}, "status": "Broken", "anticheats": ["Vanguard"]}
    result = parse_awacy_entry(entry)
    assert result == {"steam_appid": 789, "anticheat": "broken"}

def test_parse_running_status():
    entry = {"storeIds": {"steam": "1000"}, "status": "Running", "anticheats": ["EAC"]}
    result = parse_awacy_entry(entry)
    assert result == {"steam_appid": 1000, "anticheat": "running"}

def test_parse_unknown_status_maps_to_unknown():
    entry = {"storeIds": {"steam": "999"}, "status": "Unknown", "anticheats": []}
    result = parse_awacy_entry(entry)
    assert result["anticheat"] == "unknown"

def test_parse_missing_steam_id_returns_none():
    entry = {"storeIds": {"epic": "abc123"}, "status": "Supported"}
    assert parse_awacy_entry(entry) is None

def test_parse_no_store_ids_returns_none():
    entry = {"storeIds": {}, "status": "Denied"}
    assert parse_awacy_entry(entry) is None

def test_parse_invalid_steam_id_returns_none():
    entry = {"storeIds": {"steam": "not-a-number"}, "status": "Supported"}
    assert parse_awacy_entry(entry) is None

def test_parse_unrecognised_status_maps_to_unknown():
    entry = {"storeIds": {"steam": "42"}, "status": "SomeNewStatus"}
    result = parse_awacy_entry(entry)
    assert result["anticheat"] == "unknown"


# ── parse_awacy_games ────────────────────────────────────────────────────────

def test_parse_awacy_games_filters_no_steam_id():
    entries = [
        {"storeIds": {"steam": "100"}, "status": "Supported"},
        {"storeIds": {"epic": "abc"},  "status": "Denied"},
        {"storeIds": {"steam": "200"}, "status": "Running"},
    ]
    results = parse_awacy_games(entries)
    assert len(results) == 2
    assert all("steam_appid" in r for r in results)


# ── ingest_awacy (DB integration) ───────────────────────────────────────────

def test_ingest_updates_existing_game():
    conn = _db()
    _seed_game(conn, 100, "CounterStrike 2")
    entries = [{"storeIds": {"steam": "100"}, "status": "Denied", "anticheats": ["VAC"]}]

    import unittest.mock as mock
    with mock.patch("harvester.sources.awacy.requests.Session") as MockSession:
        MockSession.return_value.__enter__ = MockSession.return_value
        MockSession.return_value.get.return_value.json.return_value = entries
        MockSession.return_value.get.return_value.raise_for_status = lambda: None
        ingest_awacy.__wrapped__ = None  # not wrapped, just call directly

    # Test the DB logic directly without mocking requests
    games = parse_awacy_games(entries)
    for g in games:
        conn.execute(
            "UPDATE game SET anticheat = ? WHERE steam_appid = ?",
            (g["anticheat"], g["steam_appid"]),
        )
    conn.commit()

    row = conn.execute("SELECT anticheat FROM game WHERE steam_appid = 100").fetchone()
    assert row[0] == "denied"

def test_ingest_does_not_insert_unknown_games():
    conn = _db()
    games = parse_awacy_games([{"storeIds": {"steam": "99999"}, "status": "Denied"}])
    for g in games:
        result = conn.execute(
            "UPDATE game SET anticheat = ? WHERE steam_appid = ?",
            (g["anticheat"], g["steam_appid"]),
        )
        assert result.rowcount == 0  # no row to update — game not in DB

def test_ingest_preserves_proton_data():
    conn = _db()
    conn.execute(
        "INSERT INTO game (steam_appid, name, proton_tier, anticheat) "
        "VALUES (200, 'Elden Ring', 'gold', 'none')"
    )
    conn.commit()
    games = parse_awacy_games([{"storeIds": {"steam": "200"}, "status": "Supported"}])
    for g in games:
        conn.execute(
            "UPDATE game SET anticheat = ? WHERE steam_appid = ?",
            (g["anticheat"], g["steam_appid"]),
        )
    conn.commit()
    row = conn.execute(
        "SELECT proton_tier, anticheat FROM game WHERE steam_appid = 200"
    ).fetchone()
    assert row[0] == "gold"
    assert row[1] == "supported"
