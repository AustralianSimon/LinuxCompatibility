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


def build(output: Path, skip_network: bool = False, limit: int | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    if not skip_network:
        _ingest_protondb(conn, limit=limit)
        _ingest_flathub(conn)
        _ingest_winehq(conn)
        _ingest_pci_ids(conn)
        _ingest_anticheat(conn)

    _apply_overrides(conn, OVERRIDES_DIR)
    conn.commit()
    conn.close()

    if limit is not None:
        print(f"DB written to {output} (dev run, validation skipped)")
    else:
        validate_db(output)
        print(f"DB written to {output}")


def _ingest_protondb(conn: sqlite3.Connection, limit: int | None = None) -> None:
    """Fetch ProtonDB summary data and upsert into game table."""
    from .sources.protondb import ingest_protondb
    ingest_protondb(conn, limit=limit)


def _ingest_flathub(conn: sqlite3.Connection) -> None:
    """Fetch Flathub app index and upsert app + app_package rows."""
    # TODO: implement in Phase 2
    pass


def _ingest_winehq(conn: sqlite3.Connection) -> None:
    """Scrape WineHQ AppDB and upsert app rows for unmatched apps."""
    # TODO: implement in Phase 2
    pass


def _ingest_pci_ids(conn: sqlite3.Connection) -> None:
    """Download and parse pci.ids; populate hardware table from kernel driver data."""
    # TODO: implement in Phase 2
    pass


def _ingest_anticheat(conn: sqlite3.Connection) -> None:
    """Fetch AreWeAntiCheatYet data and update game.anticheat field."""
    # TODO: implement in Phase 2
    pass


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
    conn.execute(
        "INSERT OR REPLACE INTO app VALUES (?,?,?,?,?,?,?,?,date('now'))",
        (e["app_id"], e["name"], e.get("publisher"), e.get("category"),
         e["verdict"], e.get("confidence", "high"), int(e.get("linux_native", 0)),
         e.get("notes")),
    )
    for alias in e.get("aliases", []):
        conn.execute(
            "INSERT OR IGNORE INTO app_alias VALUES (?,?,'curated')", (alias, e["app_id"])
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
    args = parser.parse_args()
    build(Path(args.output), skip_network=args.skip_network, limit=args.limit)


if __name__ == "__main__":
    main()
