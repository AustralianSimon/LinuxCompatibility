"""
Tests for the Flathub ingest — all HTTP mocked, no network required.
AppStream XML fixtures are built in-process using xml.etree.ElementTree
and verified against the live API shape captured during development.
"""
import gzip
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harvester.sources.flathub import ingest_flathub, parse_flathub_component

SCHEMA = (
    Path(__file__).parent.parent.parent
    / "app" / "src" / "linuxready" / "db" / "schema.sql"
)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def _make_appstream(*components: dict) -> bytes:
    """Build a minimal gzipped AppStream XML for testing."""
    root = ET.Element("components", version="0.8")
    for c in components:
        comp = ET.SubElement(root, "component", type=c.get("type", "desktop-application"))
        ET.SubElement(comp, "id").text = c["id"]
        ET.SubElement(comp, "name").text = c["name"]
        if c.get("summary"):
            ET.SubElement(comp, "summary").text = c["summary"]
        if c.get("developer_name"):
            ET.SubElement(comp, "developer_name").text = c["developer_name"]
        if c.get("categories"):
            cats = ET.SubElement(comp, "categories")
            for cat in c["categories"]:
                ET.SubElement(cats, "category").text = cat
        if c.get("verified"):
            custom = ET.SubElement(comp, "custom")
            val = ET.SubElement(custom, "value")
            val.set("key", "flathub::verification::verified")
            val.text = "true"
    return gzip.compress(ET.tostring(root, encoding="unicode").encode("utf-8"))


def _mock_response(content: bytes):
    mock = MagicMock()
    mock.content = content
    mock.raise_for_status.return_value = None
    return mock


# ── parse_flathub_component ───────────────────────────────────────────────────

def _make_comp(data: dict) -> ET.Element:
    content = _make_appstream(data)
    root = ET.fromstring(gzip.decompress(content).decode("utf-8"))
    return root.find(".//component")


def test_parse_returns_correct_fields():
    comp = _make_comp({
        "id": "org.inkscape.Inkscape",
        "name": "Inkscape",
        "summary": "Vector graphics editor",
        "developer_name": "Inkscape Team",
        "categories": ["Graphics"],
        "verified": True,
    })
    result = parse_flathub_component(comp)
    assert result == {
        "flat_id": "org.inkscape.Inkscape",
        "name": "Inkscape",
        "summary": "Vector graphics editor",
        "publisher": "Inkscape Team",
        "category": "creative",
        "verdict": "native",
    }


def test_parse_unverified_gives_packaged():
    comp = _make_comp({"id": "org.foo.Bar", "name": "Bar", "categories": ["Utility"]})
    result = parse_flathub_component(comp)
    assert result is not None
    assert result["verdict"] == "packaged"


def test_parse_game_returns_none():
    comp = _make_comp({"id": "io.itch.foo", "name": "My Game", "categories": ["Game"]})
    assert parse_flathub_component(comp) is None


def test_parse_non_desktop_returns_none():
    comp = _make_comp({"id": "org.foo.Runtime", "name": "Runtime", "type": "runtime"})
    assert parse_flathub_component(comp) is None


def test_parse_missing_name_returns_none():
    root = ET.Element("components")
    comp = ET.SubElement(root, "component", type="desktop-application")
    ET.SubElement(comp, "id").text = "org.foo.App"
    assert parse_flathub_component(comp) is None


def test_parse_category_mapping():
    comp = _make_comp({"id": "org.foo.App", "name": "Dev Tool", "categories": ["Development"]})
    result = parse_flathub_component(comp)
    assert result["category"] == "dev"


def test_parse_unknown_category_defaults_to_utility():
    comp = _make_comp({"id": "org.foo.App", "name": "Thing", "categories": ["Photography"]})
    result = parse_flathub_component(comp)
    assert result["category"] == "utility"


# ── ingest_flathub (mocked HTTP) ─────────────────────────────────────────────

@patch("harvester.sources.flathub.requests.Session")
def test_ingest_inserts_app_and_package(MockSession, db):
    content = _make_appstream(
        {"id": "org.inkscape.Inkscape", "name": "Inkscape", "categories": ["Graphics"], "verified": True}
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    apps, packages = ingest_flathub(db)

    assert apps == 1
    assert packages == 1
    row = db.execute(
        "SELECT verdict, linux_native, confidence FROM app WHERE app_id = 'org.inkscape.Inkscape'"
    ).fetchone()
    assert row == ("native", 1, "high")


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_filters_games(MockSession, db):
    content = _make_appstream(
        {"id": "org.inkscape.Inkscape", "name": "Inkscape", "categories": ["Graphics"]},
        {"id": "io.itch.MyGame", "name": "My Game", "categories": ["Game"]},
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    apps, packages = ingest_flathub(db)

    assert apps == 1
    assert packages == 1
    assert db.execute("SELECT COUNT(*) FROM app WHERE app_id = 'io.itch.MyGame'").fetchone()[0] == 0


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_verified_native_unverified_packaged(MockSession, db):
    content = _make_appstream(
        {"id": "org.gimp.GIMP", "name": "GIMP", "categories": ["Graphics"], "verified": True},
        {"id": "org.community.Tool", "name": "Community Tool", "categories": ["Utility"]},
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    ingest_flathub(db)

    gimp_verdict = db.execute("SELECT verdict FROM app WHERE app_id = 'org.gimp.GIMP'").fetchone()[0]
    tool_verdict = db.execute("SELECT verdict FROM app WHERE app_id = 'org.community.Tool'").fetchone()[0]
    assert gimp_verdict == "native"
    assert tool_verdict == "packaged"


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_creates_alias(MockSession, db):
    content = _make_appstream(
        {"id": "org.videolan.VLC", "name": "VLC media player", "categories": ["AudioVideo"]}
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    ingest_flathub(db)

    row = db.execute(
        "SELECT app_id, source FROM app_alias WHERE alias_norm = 'vlc media player'"
    ).fetchone()
    assert row == ("org.videolan.VLC", "upstream")


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_creates_install_hint(MockSession, db):
    content = _make_appstream(
        {"id": "com.obsproject.Studio", "name": "OBS Studio", "categories": ["AudioVideo"]}
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    ingest_flathub(db)

    hint = db.execute(
        "SELECT install_hint FROM app_package WHERE app_id = 'com.obsproject.Studio'"
    ).fetchone()[0]
    assert hint == "flatpak install flathub com.obsproject.Studio"


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_second_run_no_duplicate_packages(MockSession, db):
    """Running ingest twice must not accumulate app_package rows."""
    content = _make_appstream(
        {"id": "org.inkscape.Inkscape", "name": "Inkscape", "categories": ["Graphics"]}
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    ingest_flathub(db)
    MockSession.return_value.get.return_value = _mock_response(content)
    ingest_flathub(db)

    count = db.execute(
        "SELECT COUNT(*) FROM app_package WHERE app_id = 'org.inkscape.Inkscape'"
    ).fetchone()[0]
    assert count == 1


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_does_not_overwrite_curated_app(MockSession, db):
    """INSERT OR IGNORE: a pre-existing app row (e.g. from curated seed) wins."""
    db.execute(
        "INSERT INTO app VALUES ('org.gimp.GIMP','GIMP',NULL,'creative','replace','high',0,NULL,date('now'))"
    )
    db.commit()

    content = _make_appstream(
        {"id": "org.gimp.GIMP", "name": "GIMP", "categories": ["Graphics"], "verified": True}
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    apps, packages = ingest_flathub(db)

    assert apps == 0  # not inserted (already existed)
    assert packages == 1  # package row is always added
    verdict = db.execute("SELECT verdict FROM app WHERE app_id = 'org.gimp.GIMP'").fetchone()[0]
    assert verdict == "replace"  # original value preserved


@patch("harvester.sources.flathub.requests.Session")
def test_ingest_returns_counts(MockSession, db):
    content = _make_appstream(
        {"id": "org.app.One", "name": "One", "categories": ["Utility"]},
        {"id": "org.app.Two", "name": "Two", "categories": ["Office"]},
        {"id": "io.game.Game", "name": "Game", "categories": ["Game"]},  # skipped
    )
    MockSession.return_value.get.return_value = _mock_response(content)

    apps, packages = ingest_flathub(db)

    assert apps == 2
    assert packages == 2
