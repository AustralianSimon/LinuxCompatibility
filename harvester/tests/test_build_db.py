"""
Tests for build_db helpers — particularly _upsert_app, which must handle
aliases, alternatives, and packages from curated YAML overrides.
"""
import sqlite3
from pathlib import Path

import pytest

from harvester.build_db import _upsert_app

SCHEMA = (
    Path(__file__).parent.parent.parent
    / "app" / "src" / "linuxready" / "db" / "schema.sql"
)


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield conn
    conn.close()


# ── app row ───────────────────────────────────────────────────────────────────

def test_upsert_inserts_app_row(db):
    _upsert_app(db, {
        "app_id": "test.app", "name": "Test App",
        "verdict": "native", "linux_native": 1,
    })
    row = db.execute("SELECT name, verdict FROM app WHERE app_id = 'test.app'").fetchone()
    assert row == ("Test App", "native")


def test_upsert_replaces_existing_app_row(db):
    _upsert_app(db, {"app_id": "test.app", "name": "Old Name", "verdict": "packaged"})
    _upsert_app(db, {"app_id": "test.app", "name": "New Name", "verdict": "native"})
    row = db.execute("SELECT name, verdict FROM app WHERE app_id = 'test.app'").fetchone()
    assert row == ("New Name", "native")


def test_upsert_defaults_confidence_to_high(db):
    _upsert_app(db, {"app_id": "test.app", "name": "App", "verdict": "native"})
    conf = db.execute("SELECT confidence FROM app WHERE app_id = 'test.app'").fetchone()[0]
    assert conf == "high"


# ── aliases ───────────────────────────────────────────────────────────────────

def test_upsert_inserts_aliases(db):
    _upsert_app(db, {
        "app_id": "test.app", "name": "App", "verdict": "native",
        "aliases": ["my app", "myapp"],
    })
    rows = db.execute(
        "SELECT alias_norm, source FROM app_alias WHERE app_id = 'test.app' ORDER BY alias_norm"
    ).fetchall()
    assert ("my app", "curated") in rows
    assert ("myapp", "curated") in rows


def test_upsert_alias_insert_or_ignore(db):
    _upsert_app(db, {"app_id": "test.app", "name": "App", "verdict": "native",
                     "aliases": ["my app"]})
    _upsert_app(db, {"app_id": "test.app", "name": "App", "verdict": "native",
                     "aliases": ["my app"]})
    count = db.execute(
        "SELECT COUNT(*) FROM app_alias WHERE alias_norm = 'my app'"
    ).fetchone()[0]
    assert count == 1


# ── alternatives ──────────────────────────────────────────────────────────────

def test_upsert_inserts_alternatives(db):
    _upsert_app(db, {
        "app_id": "adobe.photoshop", "name": "Adobe Photoshop",
        "verdict": "replace",
        "alternatives": [
            {"alt_app_id": "gimp.gimp", "alt_name": "GIMP", "rank": 1,
             "rationale": "Full-featured raster editor", "caveat": "Steeper learning curve"},
            {"alt_app_id": "krita.krita", "alt_name": "Krita", "rank": 2,
             "rationale": "Great for painting", "caveat": None},
        ],
    })
    rows = db.execute(
        "SELECT alt_app_id, alt_name, rank, rationale, caveat "
        "FROM app_alternative WHERE app_id = 'adobe.photoshop' ORDER BY rank"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0] == ("gimp.gimp", "GIMP", 1, "Full-featured raster editor", "Steeper learning curve")
    assert rows[1] == ("krita.krita", "Krita", 2, "Great for painting", None)


def test_upsert_alternatives_replace_on_rerun(db):
    _upsert_app(db, {
        "app_id": "adobe.photoshop", "name": "Adobe Photoshop", "verdict": "replace",
        "alternatives": [
            {"alt_app_id": "gimp.gimp", "alt_name": "GIMP", "rank": 1,
             "rationale": "Old rationale", "caveat": None},
        ],
    })
    _upsert_app(db, {
        "app_id": "adobe.photoshop", "name": "Adobe Photoshop", "verdict": "replace",
        "alternatives": [
            {"alt_app_id": "gimp.gimp", "alt_name": "GIMP", "rank": 1,
             "rationale": "Updated rationale", "caveat": "New caveat"},
        ],
    })
    row = db.execute(
        "SELECT rationale, caveat FROM app_alternative "
        "WHERE app_id = 'adobe.photoshop' AND alt_app_id = 'gimp.gimp'"
    ).fetchone()
    assert row == ("Updated rationale", "New caveat")


def test_upsert_no_alternatives_key_is_fine(db):
    _upsert_app(db, {"app_id": "test.app", "name": "App", "verdict": "native"})
    count = db.execute(
        "SELECT COUNT(*) FROM app_alternative WHERE app_id = 'test.app'"
    ).fetchone()[0]
    assert count == 0


def test_upsert_alternatives_default_rank(db):
    _upsert_app(db, {
        "app_id": "test.app", "name": "App", "verdict": "replace",
        "alternatives": [{"alt_app_id": "alt.app", "alt_name": "Alt"}],
    })
    rank = db.execute(
        "SELECT rank FROM app_alternative WHERE app_id = 'test.app'"
    ).fetchone()[0]
    assert rank == 99


# ── packages ──────────────────────────────────────────────────────────────────

def test_upsert_inserts_packages(db):
    _upsert_app(db, {
        "app_id": "mozilla.firefox", "name": "Firefox",
        "verdict": "native", "linux_native": 1,
        "packages": [
            {"ecosystem": "flatpak", "package_id": "org.mozilla.firefox",
             "is_official": 1, "install_hint": "flatpak install flathub org.mozilla.firefox"},
            {"ecosystem": "apt", "package_id": "firefox",
             "is_official": 1, "install_hint": "sudo apt install firefox"},
        ],
    })
    rows = db.execute(
        "SELECT ecosystem, package_id, install_hint FROM app_package "
        "WHERE app_id = 'mozilla.firefox' ORDER BY ecosystem"
    ).fetchall()
    assert len(rows) == 2
    assert ("apt", "firefox", "sudo apt install firefox") in rows
    assert ("flatpak", "org.mozilla.firefox", "flatpak install flathub org.mozilla.firefox") in rows


def test_upsert_packages_insert_or_ignore(db):
    _upsert_app(db, {
        "app_id": "mozilla.firefox", "name": "Firefox", "verdict": "native",
        "packages": [{"ecosystem": "apt", "package_id": "firefox",
                      "install_hint": "sudo apt install firefox"}],
    })
    _upsert_app(db, {
        "app_id": "mozilla.firefox", "name": "Firefox", "verdict": "native",
        "packages": [{"ecosystem": "apt", "package_id": "firefox",
                      "install_hint": "sudo apt install firefox"}],
    })
    count = db.execute(
        "SELECT COUNT(*) FROM app_package WHERE app_id = 'mozilla.firefox'"
    ).fetchone()[0]
    assert count == 1


def test_upsert_no_packages_key_is_fine(db):
    _upsert_app(db, {"app_id": "test.app", "name": "App", "verdict": "native"})
    count = db.execute(
        "SELECT COUNT(*) FROM app_package WHERE app_id = 'test.app'"
    ).fetchone()[0]
    assert count == 0
