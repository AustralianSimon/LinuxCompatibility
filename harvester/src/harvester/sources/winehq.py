"""
WineHQ AppDB ingest.
Fetches app lists filtered by rating tier using GET pagination.
Processes tiers best-first (Platinum → Bronze) so INSERT OR IGNORE preserves
the best available verdict when an app appears in multiple tiers.
"""
import re
import time

import requests

from ..normalize import normalize

_BASE = "https://appdb.winehq.org/objectManager.php"
_UA = "linuxready-harvester/0.1 (github.com/AustralianSimon/LinuxCompatibility)"

# Best → worst; INSERT OR IGNORE means first write wins
_TIERS = ["Platinum", "Gold", "Silver", "Bronze"]

_VERDICT_MAP = {
    "Platinum": "layer_excellent",
    "Gold":     "layer_excellent",
    "Silver":   "layer_workable",
    "Bronze":   "layer_poor",
}

_NOTES_MAP = {
    "Platinum": "WineHQ AppDB: Platinum — runs flawlessly via Wine",
    "Gold":     "WineHQ AppDB: Gold — runs well via Wine with minor issues",
    "Silver":   "WineHQ AppDB: Silver — runs with some issues via Wine",
    "Bronze":   "WineHQ AppDB: Bronze — runs with major issues via Wine",
}

# Matches app links in the listing table rows (not sidebar/header links)
_APP_RE = re.compile(r'sClass=application&amp;iId=(\d+)">(.*?)</a>')
_PAGES_RE = re.compile(r'Page <b>1</b> of <b>(\d+)</b>')


def _page_url(rating: str, page: int) -> str:
    return (
        f"{_BASE}?bIsQueue=false&bIsRejected=false&sClass=application"
        f"&sTitle=&iItemsPerPage=200&iPage={page}"
        f"&iappVersion-ratingOp0=5&sappVersion-ratingData0={rating}"
        f"&sOrderBy=appId&bAscending=true"
    )


def parse_winehq_page(html: str) -> list[tuple[int, str]]:
    """Extract (winehq_id, name) pairs from a WineHQ filtered app list page."""
    return [(int(aid), name.strip()) for aid, name in _APP_RE.findall(html) if name.strip()]


def _total_pages(html: str) -> int:
    m = _PAGES_RE.search(html)
    return int(m.group(1)) if m else 1


def ingest_winehq(conn, delay: float = 2.0) -> int:
    """
    Fetch WineHQ AppDB filtered app lists and upsert app + app_alias rows.
    Returns apps_inserted (new rows only).
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    apps_inserted = 0

    for rating in _TIERS:
        verdict = _VERDICT_MAP[rating]
        notes = _NOTES_MAP[rating]

        print(f"  WineHQ: fetching {rating} tier…", flush=True)
        resp = session.get(_page_url(rating, 1), timeout=90)
        resp.raise_for_status()
        first_html = resp.content.decode("utf-8", errors="replace")
        total = _total_pages(first_html)
        print(f"  WineHQ: {rating} — {total} page(s)", flush=True)

        for page in range(1, total + 1):
            html = first_html if page == 1 else _fetch_page(session, rating, page, delay)

            for app_id_int, name in parse_winehq_page(html):
                app_id = f"winehq.{app_id_int}"
                result = conn.execute(
                    "INSERT OR IGNORE INTO app "
                    "(app_id, name, publisher, category, verdict, confidence, linux_native, notes, updated_at) "
                    "VALUES (?, ?, NULL, 'utility', ?, 'medium', 0, ?, date('now'))",
                    (app_id, name, verdict, notes),
                )
                if result.rowcount:
                    apps_inserted += 1
                    conn.execute(
                        "INSERT OR IGNORE INTO app_alias (alias_norm, app_id, source) "
                        "VALUES (?, ?, 'upstream')",
                        (normalize(name), app_id),
                    )

            if page % 5 == 0:
                conn.commit()
                print(f"  WineHQ: {rating} — page {page}/{total}", flush=True)

        conn.commit()
        print(f"  WineHQ: {rating} done", flush=True)
        time.sleep(delay)

    print(f"  WineHQ: {apps_inserted} new app rows total", flush=True)
    return apps_inserted


def _fetch_page(session: requests.Session, rating: str, page: int, delay: float) -> str:
    time.sleep(delay)
    resp = session.get(_page_url(rating, page), timeout=90)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")
