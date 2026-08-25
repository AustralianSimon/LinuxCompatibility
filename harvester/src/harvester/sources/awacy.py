"""
AreWeAntiCheatYet ingest.

Downloads the public games.json and updates the anticheat column on game rows
that are already in the DB (from the ProtonDB ingest). Games not already present
are skipped — we only annotate, not create rows.

Source: https://github.com/AreWeAntiCheatYet/AreWeAntiCheatYet
"""
import requests

_AWACY_URL = (
    "https://raw.githubusercontent.com/"
    "AreWeAntiCheatYet/AreWeAntiCheatYet/master/games.json"
)

_UA = "linuxready-harvester/0.1 (github.com/AustralianSimon/LinuxCompatibility)"

_STATUS_MAP = {
    "Supported": "supported",
    "Running":   "running",
    "Denied":    "denied",
    "Broken":    "broken",
}


# ── pure parsers (I/O-free, testable) ──────────────────────────────────────

def parse_awacy_entry(entry: dict) -> dict | None:
    """
    Return {steam_appid, anticheat} from one AWACY games.json entry,
    or None if the entry has no Steam ID or an invalid one.
    """
    steam_id = (entry.get("storeIds") or {}).get("steam")
    if not steam_id:
        return None
    try:
        appid = int(steam_id)
    except (ValueError, TypeError):
        return None
    status = entry.get("status", "Unknown")
    return {
        "steam_appid": appid,
        "anticheat":   _STATUS_MAP.get(status, "unknown"),
    }


def parse_awacy_games(entries: list[dict]) -> list[dict]:
    """Filter and parse a full AWACY games list. Returns only entries with Steam IDs."""
    results = []
    for entry in entries:
        parsed = parse_awacy_entry(entry)
        if parsed is not None:
            results.append(parsed)
    return results


# ── network + ingest ────────────────────────────────────────────────────────

def ingest_awacy(conn) -> int:
    """
    Download AWACY games.json and update the anticheat column on game rows
    that already exist in the DB. Returns the number of rows updated.
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    print("  Downloading AreWeAntiCheatYet games.json…", flush=True)
    resp = session.get(_AWACY_URL, timeout=30)
    resp.raise_for_status()
    entries = resp.json()

    games = parse_awacy_games(entries)
    print(f"  AWACY: {len(games):,} entries with Steam IDs", flush=True)

    updated = 0
    for g in games:
        result = conn.execute(
            "UPDATE game SET anticheat = ?, updated_at = date('now') "
            "WHERE steam_appid = ?",
            (g["anticheat"], g["steam_appid"]),
        )
        updated += result.rowcount

    conn.commit()
    print(f"  AWACY: {updated:,} game rows updated", flush=True)
    return updated
