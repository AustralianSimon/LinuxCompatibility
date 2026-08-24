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
_SCHEMA = ROOT / "src" / "linuxready" / "db" / "schema.sql"


def _mem_db():
    """In-memory DB with schema for game_alias cascade tests."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


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
    assert result.matched_id == "570"
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


# ── game_alias cascade (Epic/GOG path) ────────────────────────────────────────

def _seed_game_alias(conn, appid: int, name: str, launcher: str = "steam") -> None:
    conn.execute(
        "INSERT INTO game (steam_appid, name) VALUES (?, ?)", (appid, name)
    )
    conn.execute(
        "INSERT INTO game_alias (alias_norm, steam_appid, launcher, launcher_id) "
        "VALUES (?, ?, ?, ?)",
        (normalize(name), appid, launcher, str(appid)),
    )
    conn.commit()


def test_epic_game_resolves_via_game_alias():
    conn = _mem_db()
    _seed_game_alias(conn, 1145360, "Hades", launcher="steam")
    item = RawItem(source="epic", raw_name="Hades", raw_keys={"catalog_item_id": "abc123"})
    result = resolve(item, conn)
    assert result.matched_id == "1145360"
    assert result.match_tier == 3


def test_gog_game_resolves_via_game_alias():
    conn = _mem_db()
    _seed_game_alias(conn, 1091500, "Cyberpunk 2077", launcher="steam")
    item = RawItem(source="gog", raw_name="Cyberpunk 2077", raw_keys={"gog_product_id": "123"})
    result = resolve(item, conn)
    assert result.matched_id == "1091500"
    assert result.match_tier == 3


def test_game_alias_returns_none_when_no_match():
    conn = _mem_db()
    item = RawItem(source="epic", raw_name="zzz_not_a_real_game", raw_keys={})
    result = resolve(item, conn)
    assert result.matched_id is None
    assert result.match_confidence == "unknown"


def test_game_alias_curated_wins_over_steam_launcher():
    conn = _mem_db()
    _seed_game_alias(conn, 1145360, "Hades", launcher="steam")
    # Curated entry points to a different appid (override scenario)
    conn.execute("INSERT INTO game (steam_appid, name) VALUES (9999999, 'Hades Alt')")
    conn.execute(
        "INSERT INTO game_alias (alias_norm, steam_appid, launcher, launcher_id) "
        "VALUES (?, 9999999, 'curated', NULL)",
        (normalize("Hades"),),
    )
    conn.commit()
    item = RawItem(source="epic", raw_name="Hades", raw_keys={})
    result = resolve(item, conn)
    assert result.matched_id == "9999999"
    assert result.match_tier == 2


def test_steam_game_source_uses_game_alias_path():
    conn = _mem_db()
    _seed_game_alias(conn, 570, "Dota 2", launcher="steam")
    # No steam_appid in raw_keys — falls through to game_alias
    item = RawItem(source="steam", raw_name="Dota 2", raw_keys={})
    result = resolve(item, conn)
    assert result.matched_id == "570"


def test_xbox_game_resolves_via_game_alias():
    conn = _mem_db()
    _seed_game_alias(conn, 1716740, "Halo Infinite", launcher="steam")
    item = RawItem(source="xbox", raw_name="Halo Infinite",
                   raw_keys={"package_name": "Microsoft.HaloInfinite_8wekyb3d8bbwe"})
    result = resolve(item, conn)
    assert result.matched_id == "1716740"
    assert result.match_tier == 3


def test_xbox_source_uses_game_path_not_app_path():
    """Xbox items must reach _cascade_game, not _cascade_app."""
    conn = _mem_db()
    # Seed a game alias — only reachable via _cascade_game
    _seed_game_alias(conn, 1716740, "Halo Infinite", launcher="steam")
    # Seed an app alias with the same name — must NOT be returned
    conn.execute(
        "INSERT INTO app (app_id, name, verdict, confidence, linux_native) "
        "VALUES ('app.halo', 'Halo Infinite', 'packaged', 'medium', 0)"
    )
    conn.execute(
        "INSERT INTO app_alias (alias_norm, app_id, source) VALUES (?, 'app.halo', 'upstream')",
        (normalize("Halo Infinite"),),
    )
    conn.commit()
    item = RawItem(source="xbox", raw_name="Halo Infinite", raw_keys={})
    result = resolve(item, conn)
    assert result.matched_id == "1716740"  # game, not app
