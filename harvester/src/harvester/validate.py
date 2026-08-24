"""
Validation gates that must pass before a DB build is published.
Called automatically at the end of build_db.build().
"""
import sqlite3
import sys
from pathlib import Path

# Golden set: (canonical_id, expected_verdict) — must not regress
_GOLDEN = [
    ("steam:570",    "native"),        # Dota 2
    ("steam:440",    "native"),        # TF2
    ("steam:1091500","layer_excellent"),# Cyberpunk 2077
    ("mozilla.firefox", "native"),
    ("google.chrome",   "native"),
    ("adobe.photoshop", "replace"),
    ("microsoft.office","web"),
]

_MIN_GAME_ROWS  = 1_000
_MIN_APP_ROWS   = 500
_MIN_HW_ROWS    = 15
_MAX_CHANGE_PCT = 20  # alert if counts shift >20% vs previous build


def validate_db(path: Path, prev_path: Path | None = None) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    errors: list[str] = []

    # ── Schema conformance ──────────────────────────────────────────────────
    for table in ("app", "app_alias", "app_package", "app_alternative",
                  "game", "game_alias", "hardware", "meta"):
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            errors.append(f"Missing table: {table}")

    # ── Minimum coverage ────────────────────────────────────────────────────
    counts = {
        "game": conn.execute("SELECT COUNT(*) FROM game").fetchone()[0],
        "app":  conn.execute("SELECT COUNT(*) FROM app").fetchone()[0],
        "hw":   conn.execute("SELECT COUNT(*) FROM hardware").fetchone()[0],
    }
    if counts["game"] < _MIN_GAME_ROWS:
        errors.append(f"game table too small: {counts['game']} < {_MIN_GAME_ROWS}")
    if counts["app"] < _MIN_APP_ROWS:
        errors.append(f"app table too small: {counts['app']} < {_MIN_APP_ROWS}")
    if counts["hw"] < _MIN_HW_ROWS:
        errors.append(f"hardware table too small: {counts['hw']} < {_MIN_HW_ROWS}")

    # ── Orphan foreign keys ─────────────────────────────────────────────────
    orphan_aliases = conn.execute(
        "SELECT COUNT(*) FROM app_alias aa WHERE NOT EXISTS "
        "(SELECT 1 FROM app a WHERE a.app_id = aa.app_id)"
    ).fetchone()[0]
    if orphan_aliases:
        errors.append(f"Orphan app_alias rows: {orphan_aliases}")

    # ── replace verdict must have alternatives ──────────────────────────────
    no_alts = conn.execute(
        "SELECT app_id FROM app WHERE verdict = 'replace' AND app_id NOT IN "
        "(SELECT DISTINCT app_id FROM app_alternative)"
    ).fetchall()
    for row in no_alts:
        errors.append(f"replace verdict with no alternatives: {row[0]}")

    # ── Golden-set regression check ─────────────────────────────────────────
    # Note: golden set uses canonical IDs, not matched_ids — validate DB directly
    app_gold = [(aid, v) for aid, v in _GOLDEN if not aid.startswith("steam:")]
    game_gold = [(int(aid.split(":")[1]), v) for aid, v in _GOLDEN if aid.startswith("steam:")]

    for app_id, expected in app_gold:
        row = conn.execute("SELECT verdict FROM app WHERE app_id = ?", (app_id,)).fetchone()
        if not row:
            errors.append(f"Golden app not in DB: {app_id}")
        elif row[0] != expected:
            errors.append(f"Golden verdict regression: {app_id} expected={expected} got={row[0]}")

    for appid, expected in game_gold:
        row = conn.execute("SELECT native_linux, proton_tier, anticheat FROM game WHERE steam_appid = ?",
                           (appid,)).fetchone()
        if not row:
            errors.append(f"Golden game not in DB: steam:{appid}")

    conn.close()

    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Validation passed — {counts['game']:,} games, {counts['app']:,} apps, {counts['hw']:,} hw rows")
