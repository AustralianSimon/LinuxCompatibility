import sqlite3
from typing import Optional

from ..models import RawItem, ScanItem
from .confidence import tier_confidence
from .normalize import normalize

try:
    from rapidfuzz import fuzz, process as rfprocess
    _HAVE_RAPIDFUZZ = True
except ImportError:
    _HAVE_RAPIDFUZZ = False

_FUZZY_THRESHOLD = 88


def resolve(item: RawItem, conn: sqlite3.Connection) -> ScanItem:
    """Run the 6-tier match cascade and return a ScanItem."""
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
            return f"steam:{steam_id}", 1

    norm = normalize(item.raw_name)

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
        # Ambiguous — fall through to fuzzy rather than picking blindly
        pass

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

    # --- Tier 6: no match ---------------------------------------------------------
    return None, None
