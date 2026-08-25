"""
ProtonDB + SteamSpy ingest.

Game-list source : SteamSpy  (paginated, 1 000 entries/page)
Compat data      : ProtonDB  (per-game summaries/{appid}.json)
Native-Linux flag: Steam store appdetails?filters=platforms

Only games that have a ProtonDB tier are written to the DB.
Curated overrides (applied later in build_db.py) always win.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import requests

from ..normalize import normalize

log = logging.getLogger(__name__)

_STEAMSPY_URL = "https://steamspy.com/api.php"
_PROTONDB_URL = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
_STEAM_PLATFORMS_URL = "https://store.steampowered.com/api/appdetails"

_VALID_TIERS = frozenset({"platinum", "gold", "silver", "bronze", "borked"})

_UA = "linuxready-harvester/0.1 (github.com/linuxreadyami/linuxready)"


# ── sync state helpers ──────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))


def _del_meta(conn, key: str) -> None:
    conn.execute("DELETE FROM meta WHERE key = ?", (key,))


def _is_fresh(conn, max_age_hours: float) -> bool:
    """Return True if the last complete sync finished within max_age_hours."""
    completed = _get_meta(conn, "protondb_sync_completed_at")
    if not completed:
        return False
    try:
        dt = datetime.fromisoformat(completed)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) < timedelta(hours=max_age_hours)
    except ValueError:
        return False


def _begin_sync(conn) -> None:
    """Mark sync as started; if already in progress, print a resume message."""
    started = _get_meta(conn, "protondb_sync_started_at")
    if started:
        last_page = _get_meta(conn, "protondb_sync_page")
        page_info = (
            f"(last completed page: {last_page})"
            if last_page is not None
            else "(no pages completed)"
        )
        print(f"  Resuming interrupted sync from {started} {page_info}", flush=True)
    else:
        _set_meta(conn, "protondb_sync_started_at", _utcnow())
        conn.commit()


def _mark_sync_complete(conn) -> None:
    _set_meta(conn, "protondb_sync_completed_at", _utcnow())
    _del_meta(conn, "protondb_sync_started_at")
    _del_meta(conn, "protondb_sync_page")
    conn.commit()


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
    start_page: int = 0,
    max_retries: int = 3,
) -> Iterator[tuple[int, list[dict]]]:
    """Yield (page_num, games_list) for each SteamSpy page starting from start_page."""
    page = start_page
    while True:
        print(f"  SteamSpy page {page}…", flush=True)
        data = _fetch_steamspy_page(session, page, max_retries=max_retries)
        if data is None:
            print(f"  SteamSpy: no more pages after page {page}", flush=True)
            break
        print(f"  SteamSpy page {page} — {len(data):,} entries", flush=True)
        yield page, list(data.values())
        page += 1
        time.sleep(delay)


def _fetch_steamspy_page(
    session: requests.Session,
    page: int,
    *,
    max_retries: int = 3,
) -> dict | None:
    """
    Fetch one SteamSpy page, returning the parsed JSON dict.
    Returns None when SteamSpy reports no entries (end of data).
    Retries on transient errors (empty body, connection errors, 5xx) with
    exponential backoff. Raises RuntimeError if all retries are exhausted.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(
                _STEAMSPY_URL,
                params={"request": "all", "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            if not resp.text.strip():
                # Empty/whitespace-only body = SteamSpy's "no more pages" signal.
                return None
            data = resp.json()
            return data if data else None
        except (json.JSONDecodeError, ValueError) as exc:
            body = getattr(resp, "text", "") or ""
            if "Connection failed" in body or "Too many connections" in body:
                # SteamSpy returns this MySQL error when pagination is exhausted,
                # not a transient failure — treat it as clean end-of-data.
                log.info("SteamSpy page %d: '%s' — end of data", page, body.strip())
                print(f"  SteamSpy page {page}: end of data ({body.strip()[:60]})", flush=True)
                return None
            _retry_or_raise(exc, attempt, max_retries,
                            f"SteamSpy page {page}: invalid JSON body")
        except requests.ConnectionError as exc:
            _retry_or_raise(exc, attempt, max_retries,
                            f"SteamSpy page {page}: connection error")
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code >= 500:
                _retry_or_raise(exc, attempt, max_retries,
                                f"SteamSpy page {page}: server error {code}")
            else:
                raise
    return None  # unreachable; satisfies type checker


def _retry_or_raise(exc: Exception, attempt: int, max_retries: int, label: str, *, base_wait: int = 10) -> None:
    """Sleep with exponential backoff or re-raise if retries are exhausted."""
    if attempt < max_retries:
        wait = base_wait * (2 ** attempt)
        log.warning("%s (retry %d/%d in %ds): %s", label, attempt + 1, max_retries, wait, exc)
        print(f"  {label} — retrying in {wait}s ({attempt + 1}/{max_retries})…", flush=True)
        time.sleep(wait)
    else:
        raise RuntimeError(f"{label} — all {max_retries} retries exhausted: {exc}") from exc


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
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code >= 500 and attempt < max_retries:
                wait = 5 * (2 ** attempt)
                log.warning("ProtonDB server error %d for appid %s (retry %d/%d in %ds)",
                            code, appid, attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                log.warning("ProtonDB fetch failed for appid %s: %s", appid, exc)
                time.sleep(miss_delay)
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
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code >= 500:
                wait = 5 * (2 ** attempt)
                log.warning("Steam platforms server error %d for appid %s (retry %d in %ds)",
                            code, appid, attempt + 1, wait)
                time.sleep(wait)
            else:
                log.warning("Steam platforms fetch failed for appid %s: %s", appid, exc)
                time.sleep(delay)
                return False
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
    max_age_hours: float | None = 24.0,
    proton_delay: float = 1.0,
    spy_delay: float = 2.0,
) -> int | None:
    """
    Walk SteamSpy pages, fetch ProtonDB data for each game, upsert into
    the game table. Returns the number of rows written, or None if the
    last sync completed within max_age_hours (skipped as still fresh).

    Resume: if a previous run was interrupted, the next call starts from
    the page after the last fully-completed SteamSpy page (stored in meta
    as protondb_sync_page). The partial page is re-fetched; DB upserts
    are idempotent so re-running one page is safe.

    Set max_age_hours=None or 0 to always run regardless of last sync time.
    Sync state is not tracked when limit is set (dev/test mode).
    """
    # track_state=False keeps limit runs clean: no stale meta left behind.
    track_state = limit is None

    if track_state and max_age_hours and _is_fresh(conn, max_age_hours):
        completed = _get_meta(conn, "protondb_sync_completed_at")
        print(f"  ProtonDB: last sync {completed} (< {max_age_hours}h ago) — skipping", flush=True)
        return None

    if track_state:
        _begin_sync(conn)
        last_page = _get_meta(conn, "protondb_sync_page")
        start_page = (int(last_page) + 1) if last_page is not None else 0
    else:
        start_page = 0

    session = requests.Session()
    session.headers["User-Agent"] = _UA

    written = 0
    checked = 0

    for page_num, games in iter_steamspy_pages(session, delay=spy_delay, start_page=start_page):
        for game in games:
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
            # Populate game_alias so name-based matching works for Epic/GOG collectors.
            # INSERT OR IGNORE: curated overrides applied later are never clobbered.
            conn.execute(
                "INSERT OR IGNORE INTO game_alias (alias_norm, steam_appid, launcher, launcher_id) "
                "VALUES (?, ?, 'steam', ?)",
                (normalize(name), appid, str(appid)),
            )

            written += 1
            if written % 500 == 0:
                conn.commit()
                print(f"  ProtonDB: {written:,} written / {checked:,} checked", flush=True)
        else:
            # Inner loop completed without hitting the limit — page is fully processed.
            if track_state:
                _set_meta(conn, "protondb_sync_page", str(page_num))
                conn.commit()
            continue
        break  # limit was hit — exit outer loop without checkpointing this page

    conn.commit()
    if track_state:
        _mark_sync_complete(conn)
    return written
