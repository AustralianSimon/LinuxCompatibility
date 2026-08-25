"""
Flathub ingest.
Downloads the Flathub AppStream catalog (one gzipped XML request)
and upserts app + app_package + app_alias rows.

Verified apps (publisher-submitted, flathub::verification::verified=true) get
verdict='native'; community-maintained repackages get verdict='packaged'.
Games (AppStream category 'Game') are skipped — they belong in the game table.
"""
import gzip
import xml.etree.ElementTree as ET

import requests

from ..normalize import normalize

_APPSTREAM_URL = "https://dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz"
_UA = "linuxready-harvester/0.1 (github.com/AustralianSimon/LinuxCompatibility)"

# xml:lang attribute in Clark notation
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

_CATEGORY_MAP = {
    "AudioVideo": "utility",
    "Audio":      "utility",
    "Video":      "utility",
    "Development":"dev",
    "Education":  "utility",
    "Graphics":   "creative",
    "Network":    "utility",
    "Office":     "office",
    "Science":    "utility",
    "Security":   "security",
    "Settings":   "utility",
    "System":     "utility",
    "Utility":    "utility",
}
_DEFAULT_CATEGORY = "utility"


def _text(comp, tag: str) -> str:
    """Return unlocalized text of the first matching element (no xml:lang attr), or ''."""
    for elem in comp.findall(tag):
        if elem.get(_XML_LANG) is None and elem.text:
            return elem.text.strip()
    return ""


def _is_verified(comp) -> bool:
    """Read the Flathub verification flag from <custom> or <metadata>."""
    for container in ("custom", "metadata"):
        for val in comp.findall(f"{container}/value"):
            if val.get("key") == "flathub::verification::verified":
                return (val.text or "").strip().lower() == "true"
    return False


def parse_flathub_component(comp) -> dict | None:
    """
    Parse one AppStream <component> element.
    Returns None for non-desktop apps, games, or entries missing id/name.
    """
    if comp.get("type") != "desktop-application":
        return None

    flat_id = _text(comp, "id") or (comp.findtext("id") or "").strip()
    name = _text(comp, "name")
    if not flat_id or not name:
        return None

    categories = [c.text.strip() for c in comp.findall("categories/category") if c.text]
    if "Game" in categories:
        return None

    category = next((_CATEGORY_MAP[c] for c in categories if c in _CATEGORY_MAP), _DEFAULT_CATEGORY)
    verified = _is_verified(comp)

    return {
        "flat_id": flat_id,
        "name": name,
        "summary": _text(comp, "summary") or None,
        "publisher": _text(comp, "developer_name") or None,
        "category": category,
        "verdict": "native" if verified else "packaged",
    }


def ingest_flathub(conn) -> tuple[int, int]:
    """
    Download Flathub AppStream catalog and upsert app + app_package + app_alias rows.
    Returns (apps_inserted, packages_inserted).

    app_package rows are cleared and re-inserted on every run since that table has
    no PRIMARY KEY and cannot be cleanly upserted.
    Curated overrides (applied later by build_db.py) always win via INSERT OR REPLACE.
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    print("  Downloading Flathub AppStream catalog…", flush=True)
    resp = session.get(_APPSTREAM_URL, timeout=120)
    resp.raise_for_status()

    xml_bytes = gzip.decompress(resp.content)
    root = ET.fromstring(xml_bytes.decode("utf-8"))

    components = root.findall(".//component")
    print(f"  Flathub: {len(components):,} components in catalog", flush=True)

    # Clear existing flatpak package rows; app_package has no PK so we can't upsert.
    conn.execute("DELETE FROM app_package WHERE ecosystem = 'flatpak'")

    apps_inserted = 0
    packages_inserted = 0

    for comp in components:
        parsed = parse_flathub_component(comp)
        if parsed is None:
            continue

        flat_id = parsed["flat_id"]

        result = conn.execute(
            "INSERT OR IGNORE INTO app "
            "(app_id, name, publisher, category, verdict, confidence, linux_native, notes, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'high', 1, ?, date('now'))",
            (flat_id, parsed["name"], parsed["publisher"], parsed["category"],
             parsed["verdict"], parsed["summary"]),
        )
        if result.rowcount:
            apps_inserted += 1
            conn.execute(
                "INSERT OR IGNORE INTO app_alias (alias_norm, app_id, source) "
                "VALUES (?, ?, 'upstream')",
                (normalize(parsed["name"]), flat_id),
            )

        conn.execute(
            "INSERT INTO app_package (app_id, ecosystem, package_id, is_official, install_hint) "
            "VALUES (?, 'flatpak', ?, 1, ?)",
            (flat_id, flat_id, f"flatpak install flathub {flat_id}"),
        )
        packages_inserted += 1

        if packages_inserted % 200 == 0:
            conn.commit()
            print(f"  Flathub: {packages_inserted:,} processed", flush=True)

    conn.commit()
    print(
        f"  Flathub: {apps_inserted:,} new app rows, {packages_inserted:,} package rows",
        flush=True,
    )
    return apps_inserted, packages_inserted
