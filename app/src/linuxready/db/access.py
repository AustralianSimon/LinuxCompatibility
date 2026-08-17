import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def open_db(path: Path | str) -> Generator[sqlite3.Connection, None, None]:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None
