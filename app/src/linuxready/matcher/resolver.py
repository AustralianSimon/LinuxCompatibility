import sqlite3
from typing import Optional
from urllib.parse import urlencode

from .. import __version__
from ..config import GITHUB_REPO
from ..models import RawItem, ScanItem
from .confidence import tier_confidence
from .normalize import normalize

try:
    from rapidfuzz import fuzz, process as rfprocess
    _HAVE_RAPIDFUZZ = True
except ImportError:
    _HAVE_RAPIDFUZZ = False

_FUZZY_THRESHOLD = 88
_GAME_SOURCES = frozenset({"steam", "epic", "gog", "xbox"})


def resolve(item: RawItem, conn: sqlite3.Connection) -> ScanItem:
    """Run the match cascade and return a ScanItem."""
    matched_id, tier = _cascade(item, conn)
    return ScanItem(
        source=item.source,
        raw_name=item.raw_name,
        raw_keys=item.raw_keys,
        matched_id=matched_id,
        match_tier=tier,
        match_confidence=tier_confidence(tier) if tier else "unknown",
    )


def _cascade(item: RawItem, conn: sqlite3.Connection) -> tuple[Optional[str], Optional[int]]:
    keys = item.raw_keys

    # --- Tier 1: exact stable key -------------------------------------------------
    if steam_id := keys.get("steam_appid"):
        row = conn.execute(
            "SELECT steam_appid FROM game WHERE steam_appid = ?", (int(steam_id),)
        ).fetchone()
        if row:
            return str(steam_id), 1

    norm = normalize(item.raw_name)

    if item.source in _GAME_SOURCES:
        return _cascade_game(norm, item.source, conn)
    return _cascade_app(norm, keys, conn)


def _cascade_game(
    norm: str, source: str, conn: sqlite3.Connection
) -> tuple[Optional[str], Optional[int]]:
    # --- Tier 2: curated game alias -----------------------------------------------
    row = conn.execute(
        "SELECT steam_appid FROM game_alias WHERE alias_norm = ? AND launcher = 'curated' LIMIT 1",
        (norm,),
    ).fetchone()
    if row:
        return str(row[0]), 2

    # --- Tier 3: unique steam_appid by name (DISTINCT across all launchers) -------
    rows = conn.execute(
        "SELECT DISTINCT steam_appid FROM game_alias WHERE alias_norm = ?", (norm,)
    ).fetchall()
    if len(rows) == 1:
        return str(rows[0][0]), 3

    # --- Tier 4: launcher-specific match when multiple games share a name ---------
    if len(rows) > 1:
        row = conn.execute(
            "SELECT steam_appid FROM game_alias WHERE alias_norm = ? AND launcher = ? LIMIT 1",
            (norm, source),
        ).fetchone()
        if row:
            return str(row[0]), 4

    # --- Tier 5: fuzzy over game_alias --------------------------------------------
    if _HAVE_RAPIDFUZZ:
        all_aliases = conn.execute(
            "SELECT DISTINCT alias_norm, steam_appid FROM game_alias"
        ).fetchall()
        if all_aliases:
            choices = {alias: appid for alias, appid in all_aliases}
            hit = rfprocess.extractOne(norm, choices.keys(), scorer=fuzz.token_set_ratio)
            if hit and hit[1] >= _FUZZY_THRESHOLD:
                return str(choices[hit[0]]), 5

    return None, None


def _cascade_app(
    norm: str, keys: dict, conn: sqlite3.Connection
) -> tuple[Optional[str], Optional[int]]:
    # --- Tier 2: curated override in alias table ----------------------------------
    row = conn.execute(
        "SELECT app_id FROM app_alias WHERE alias_norm = ? AND source = 'curated' LIMIT 1",
        (norm,),
    ).fetchone()
    if row:
        return row[0], 2

    # --- Tier 3: normalised name + publisher --------------------------------------
    publisher = (keys.get("publisher") or "").strip()
    if publisher:
        pub_norm = normalize(publisher)
        row = conn.execute(
            "SELECT aa.app_id FROM app_alias aa "
            "JOIN app a ON a.app_id = aa.app_id "
            "WHERE aa.alias_norm = ? AND lower(a.publisher) LIKE ? LIMIT 1",
            (norm, f"%{pub_norm}%"),
        ).fetchone()
        if row:
            return row[0], 3

    # --- Tier 4: normalised name alone, unique ------------------------------------
    rows = conn.execute(
        "SELECT app_id FROM app_alias WHERE alias_norm = ?", (norm,)
    ).fetchall()
    if len(rows) == 1:
        return rows[0][0], 4
    if len(rows) > 1:
        pass  # Ambiguous — fall through to fuzzy

    # --- Tier 5: fuzzy via rapidfuzz ----------------------------------------------
    if _HAVE_RAPIDFUZZ:
        all_aliases = conn.execute(
            "SELECT alias_norm, app_id FROM app_alias"
        ).fetchall()
        if all_aliases:
            choices = {alias: app_id for alias, app_id in all_aliases}
            hit = rfprocess.extractOne(norm, choices.keys(),
                                       scorer=fuzz.token_set_ratio)
            if hit and hit[1] >= _FUZZY_THRESHOLD:
                return choices[hit[0]], 5

    return None, None


def bad_match_url(item: ScanItem, db_build: str) -> str:
    """
    Return a pre-filled GitHub Issue URL for reporting a wrong match.
    Opens in the user's browser — the app makes no network request.
    Only the raw name, matched ID, match metadata, and version are included;
    no hardware IDs or machine-identifying fields.
    """
    params = urlencode({
        "labels":      "bad-match",
        "template":    "bad-match.yml",
        "title":       f'Bad match: "{item.raw_name}"',
        "app_id":      item.matched_id or "none",
        "match_tier":  item.match_tier or "none",
        "confidence":  item.match_confidence or "unknown",
        "app_version": __version__,
        "db_build":    db_build,
    })
    return f"https://github.com/{GITHUB_REPO}/issues/new?{params}"
