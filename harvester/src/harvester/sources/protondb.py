"""
ProtonDB + SteamSpy ingest.

Game-list source : SteamSpy  (paginated, 1 000 entries/page)
Compat data      : ProtonDB  (per-game summaries/{appid}.json)
Native-Linux flag: Steam store appdetails?filters=platforms

Only games that have a ProtonDB tier are written to the DB.
Curated overrides (applied later in build_db.py) always win.
"""
import logging
import time
from typing import Iterator

import requests

log = logging.getLogger(__name__)

_STEAMSPY_URL = "https://steamspy.com/api.php"
_PROTONDB_URL = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
_STEAM_PLATFORMS_URL = "https://store.steampowered.com/api/appdetails"

_VALID_TIERS = frozenset({"platinum", "gold", "silver", "bronze", "borked"})

_UA = "linuxready-harvester/0.1 (github.com/linuxreadyami/linuxready)"


# ── pure parsers (I/O-free, testable) ──────────────────────────────────────

def parse_protondb_summary(data: dict) -> dict | None:
    """
    Return {proton_tier, proton_sample} from a ProtonDB summary dict,
    or None if the tier is absent, 'pending', or not a recognised value.
    """
    tier = data.get("tier")
    if not tier or tier not in _VALID_TIERS:
        return None
    return {
        "proton_tier": tier,
        "proton_sample": data.get("total"),
    }


def parse_steam_linux(data: dict, appid: int) -> bool:
    """Return True if the Steam appdetails response reports a Linux platform."""
    return bool(
        data.get(str(appid), {})
            .get("data", {})
            .get("platforms", {})
            .get("linux")
    )


# ── network helpers ─────────────────────────────────────────────────────────

def iter_steamspy_pages(
    session: requests.Session,
    *,
    delay: float = 2.0,
) -> Iterator[dict]:
    """Yield one game dict per entry across all SteamSpy pages."""
    page = 0
    while True:
        resp = session.get(
            _STEAMSPY_URL,
            params={"request": "all", "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        yield from data.values()
        page += 1
        time.sleep(delay)


def fetch_protondb_summary(
    session: requests.Session,
    appid: int,
    *,
    delay: float = 1.0,
    miss_delay: float = 0.3,
    max_retries: int = 3,
) -> dict | None:
    """
    Fetch and parse one ProtonDB summary.
    - 404 (no reports): sleeps `miss_delay` and returns None.
    - Success: sleeps `delay` and returns parsed dict (or None for pending tier).
    - Connection error: retries up to `max_retries` times with exponential backoff.
    """
    url = _PROTONDB_URL.format(appid=appid)
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 404:
                time.sleep(miss_delay)
                return None
            resp.raise_for_status()
            time.sleep(delay)
            return parse_protondb_summary(resp.json())
        except requests.ConnectionError as exc:
            if attempt < max_retries:
                wait = 5 * (2 ** attempt)  # 5 s, 10 s, 20 s
                log.warning(
                    "ProtonDB connection error for appid %s (retry %d/%d in %ds): %s",
                    appid, attempt + 1, max_retries, wait, exc,
                )
                time.sleep(wait)
            else:
                log.warning("ProtonDB fetch failed after %d retries for appid %s: %s",
                            max_retries, appid, exc)
                return None
        except requests.RequestException as exc:
            log.warning("ProtonDB fetch failed for appid %s: %s", appid, exc)
            time.sleep(miss_delay)
            return None
    return None  # unreachable, satisfies type checkers


def fetch_native_linux(session: requests.Session, appid: int, *, delay: float = 0.3) -> bool:
    """Return True if the Steam store API reports a native Linux build."""
    for attempt in range(3):
        try:
            resp = session.get(
                _STEAM_PLATFORMS_URL,
                params={"appids": appid, "filters": "platforms"},
                timeout=15,
            )
            resp.raise_for_status()
            time.sleep(delay)
            return parse_steam_linux(resp.json(), appid)
        except requests.ConnectionError as exc:
            wait = 5 * (2 ** attempt)
            log.warning("Steam platforms connection error for appid %s (retry %d in %ds): %s",
                        appid, attempt + 1, wait, exc)
            time.sleep(wait)
        except requests.RequestException as exc:
            log.warning("Steam platforms fetch failed for appid %s: %s", appid, exc)
            time.sleep(delay)
            return False
    return False


# ── main ingest ─────────────────────────────────────────────────────────────

def ingest_protondb(
    conn,
    *,
    limit: int | None = None,
    proton_delay: float = 1.0,
    spy_delay: float = 2.0,
) -> int:
    """
    Walk SteamSpy pages, fetch ProtonDB data for each game, upsert into
    the game table. Returns the number of rows written.

    Only games with a recognised ProtonDB tier are written; games with no
    reports (404) are skipped entirely rather than added as unknowns.

    The anticheat column is left untouched on updates so that
    _ingest_anticheat (runs after this) and curated overrides are not
    clobbered.
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    written = 0
    checked = 0

    for game in iter_steamspy_pages(session, delay=spy_delay):
        appid = game.get("appid")
        name = game.get("name", "").strip()
        if not appid or not name:
            continue

        checked += 1
        if limit is not None and checked > limit:
            break

        proton = fetch_protondb_summary(session, appid, delay=proton_delay)
        if proton is None:
            continue

        native = fetch_native_linux(session, appid)

        # Insert new row; on conflict update only the proton/platform columns,
        # leaving anticheat (set by _ingest_anticheat) untouched.
        conn.execute(
            """
            INSERT INTO game (steam_appid, name, native_linux, proton_tier, proton_sample,
                              anticheat, updated_at)
            VALUES (?, ?, ?, ?, ?, 'none', date('now'))
            ON CONFLICT(steam_appid) DO UPDATE SET
                name         = excluded.name,
                native_linux = excluded.native_linux,
                proton_tier  = excluded.proton_tier,
                proton_sample= excluded.proton_sample,
                updated_at   = excluded.updated_at
            """,
            (appid, name, int(native), proton["proton_tier"], proton["proton_sample"]),
        )

        written += 1
        if written % 500 == 0:
            conn.commit()
            log.info("ProtonDB ingest: %d written / %d checked", written, checked)

    conn.commit()
    log.info("ProtonDB ingest complete: %d written / %d checked", written, checked)
    return written
