"""
Harvester entry point.
Fetches data from all sources, applies curated overrides, builds compat.db.
Run: harvest  (after `pip install -e .`)
"""
import argparse
import sqlite3
from pathlib import Path

from .validate import validate_db

SCHEMA = Path(__file__).parent.parent.parent.parent / "app" / "src" / "linuxready" / "db" / "schema.sql"
OVERRIDES_DIR = Path(__file__).parent.parent.parent / "data" / "overrides"

_NETWORK_STEPS = 5


def _step(n: int, total: int, label: str, done: bool = False, detail: str = "") -> None:
    if done:
        suffix = f"  ✓  {detail}" if detail else "  ✓"
        print(f"  [{n}/{total}] {label}{suffix}", flush=True)
    else:
        print(f"\n[{n}/{total}] {label}…", flush=True)


def build(
    output: Path,
    skip_network: bool = False,
    limit: int | None = None,
    max_age_hours: float | None = 24.0,
) -> None:
    total = _NETWORK_STEPS + 1  # network steps + overrides
    step  = 0

    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    if not skip_network:
        step += 1
        _step(step, total, "ProtonDB + SteamSpy")
        written = _ingest_protondb(conn, limit=limit, max_age_hours=max_age_hours)
        if written is None:
            _step(step, total, "ProtonDB + SteamSpy", done=True, detail="skipped (synced recently)")
        else:
            _step(step, total, "ProtonDB + SteamSpy", done=True, detail=f"{written:,} games written")

        step += 1
        _step(step, total, "Flathub")
        apps_written, pkgs_written = _ingest_flathub(conn)
        _step(step, total, "Flathub", done=True, detail=f"{apps_written:,} apps, {pkgs_written:,} packages")

        step += 1
        _step(step, total, "WineHQ AppDB")
        wine_written = _ingest_winehq(conn)
        _step(step, total, "WineHQ AppDB", done=True, detail=f"{wine_written:,} apps")

        step += 1
        _step(step, total, "pci.ids hardware table")
        inserted = _ingest_pci_ids(conn)
        _step(step, total, "pci.ids hardware table", done=True, detail=f"{inserted} rows inserted")

        step += 1
        _step(step, total, "AreWeAntiCheatYet")
        updated = _ingest_anticheat(conn)
        _step(step, total, "AreWeAntiCheatYet", done=True, detail=f"{updated:,} games updated")
    else:
        total = 1  # overrides only

    step += 1
    _step(step, total, "Curated overrides")
    _apply_overrides(conn, OVERRIDES_DIR)
    _step(step, total, "Curated overrides", done=True)

    conn.commit()
    conn.close()

    print()
    if limit is not None:
        print(f"DB written to {output}  (dev run — validation skipped)")
    else:
        validate_db(output)
        print(f"DB written to {output}")


def _ingest_protondb(
    conn: sqlite3.Connection,
    limit: int | None = None,
    max_age_hours: float | None = 24.0,
) -> int | None:
    """Fetch ProtonDB summary data and upsert into game table."""
    from .sources.protondb import ingest_protondb
    return ingest_protondb(conn, limit=limit, max_age_hours=max_age_hours)


def _ingest_flathub(conn: sqlite3.Connection) -> tuple[int, int]:
    """Download Flathub AppStream catalog and upsert app + app_package rows."""
    from .sources.flathub import ingest_flathub
    return ingest_flathub(conn)


def _ingest_winehq(conn: sqlite3.Connection) -> int:
    """Fetch WineHQ AppDB filtered app lists and upsert app + app_alias rows."""
    from .sources.winehq import ingest_winehq
    return ingest_winehq(conn)


def _ingest_pci_ids(conn: sqlite3.Connection) -> int:
    """Download pci.ids and populate hardware table with vendor-level support rows."""
    from .sources.pciids import ingest_pci_ids
    return ingest_pci_ids(conn)


def _ingest_anticheat(conn: sqlite3.Connection) -> int:
    """Fetch AreWeAntiCheatYet data and update game.anticheat field."""
    from .sources.awacy import ingest_awacy
    return ingest_awacy(conn)


def _apply_overrides(conn: sqlite3.Connection, overrides_dir: Path) -> None:
    """Apply hand-curated YAML overrides — always wins over automated sources."""
    import yaml

    for yaml_file in sorted(overrides_dir.glob("*.yaml")):
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        if not data:
            continue
        for entry in data.get("apps", []):
            _upsert_app(conn, entry)
        for entry in data.get("games", []):
            _upsert_game(conn, entry)
        for entry in data.get("hardware", []):
            _upsert_hardware(conn, entry)


def _upsert_app(conn: sqlite3.Connection, e: dict) -> None:
    app_id = e["app_id"]
    conn.execute(
        "INSERT OR REPLACE INTO app VALUES (?,?,?,?,?,?,?,?,date('now'))",
        (app_id, e["name"], e.get("publisher"), e.get("category"),
         e["verdict"], e.get("confidence", "high"), int(e.get("linux_native", 0)),
         e.get("notes")),
    )
    for alias in e.get("aliases", []):
        conn.execute(
            "INSERT OR IGNORE INTO app_alias VALUES (?,?,'curated')", (alias, app_id)
        )
    if e.get("alternatives"):
        conn.execute("DELETE FROM app_alternative WHERE app_id = ?", (app_id,))
        for alt in e["alternatives"]:
            conn.execute(
                "INSERT INTO app_alternative VALUES (?,?,?,?,?,?)",
                (app_id, alt["alt_app_id"], alt["alt_name"],
                 alt.get("rank", 99), alt.get("rationale"), alt.get("caveat")),
            )
    if e.get("packages"):
        conn.execute("DELETE FROM app_package WHERE app_id = ?", (app_id,))
        for pkg in e["packages"]:
            conn.execute(
                "INSERT INTO app_package VALUES (?,?,?,?,?)",
                (app_id, pkg["ecosystem"], pkg["package_id"],
                 int(pkg.get("is_official", 1)), pkg.get("install_hint")),
            )


def _upsert_game(conn: sqlite3.Connection, e: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO game VALUES (?,?,?,?,?,?,?,?,date('now'))",
        (e["steam_appid"], e["name"], int(e.get("native_linux", 0)),
         e.get("deck_verified"), e.get("proton_tier"), e.get("proton_sample"),
         e.get("anticheat"), e.get("notes")),
    )


def _upsert_hardware(conn: sqlite3.Connection, e: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO hardware VALUES (?,?,?,?,?,?,?)",
        (e["vendor_id"], e.get("device_id"), e["class"],
         e.get("driver"), e["support"], e.get("min_kernel"), e.get("notes")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compat.db")
    parser.add_argument("--output", default="compat.db", help="Output path")
    parser.add_argument("--skip-network", action="store_true",
                        help="Apply overrides only, skip network ingestion")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Stop after checking N games (dev/testing only)")
    parser.add_argument("--max-age-hours", type=float, default=24.0, metavar="H",
                        help="Skip ProtonDB/SteamSpy sync if last complete run was less than "
                             "H hours ago (default: 24). Set to 0 to always run.")
    args = parser.parse_args()
    build(
        Path(args.output),
        skip_network=args.skip_network,
        limit=args.limit,
        max_age_hours=args.max_age_hours or None,
    )


if __name__ == "__main__":
    main()
