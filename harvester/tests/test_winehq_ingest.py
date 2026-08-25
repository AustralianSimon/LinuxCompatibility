"""
Tests for the WineHQ AppDB ingest — all HTTP mocked, no network required.
HTML fixtures are built in-process to match the real WineHQ listing structure
captured during development.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from harvester.sources.winehq import ingest_winehq, parse_winehq_page

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


def _make_list_page(
    apps: list[tuple[int, str]],
    total_pages: int = 1,
) -> str:
    """Build a minimal WineHQ listing page HTML for a given set of apps."""
    rows = "\n".join(
        f'<tr><td><a href="https://appdb.winehq.org/objectManager.php?'
        f'sClass=application&amp;iId={aid}">{name}</a></td>'
        f'<td>{aid}</td><td>Description of {name}</td></tr>'
        for aid, name in apps
    )
    total_entries = len(apps) * total_pages
    return f"""
<div class="text-center">Page <b>1</b> of <b>{total_pages}</b>
<a href="...iPage=2">2</a></div>
<p>Showing entry <b>1</b> to <b>{len(apps)}</b> of <b>{total_entries}</b></p>
<table class="whq-table whq-table-full">
<thead><tr><td>Application</td><td>Entry#</td><td>Description</td></tr></thead>
{rows}
</table>
"""


def _mock_response(html: str, status: int = 200):
    mock = MagicMock()
    mock.status_code = status
    mock.content = html.encode("utf-8")
    mock.raise_for_status.return_value = None
    return mock


# ── parse_winehq_page ─────────────────────────────────────────────────────────

def test_parse_extracts_apps():
    html = _make_list_page([(2, "WinZip"), (5, "Winamp"), (10, "Microsoft Word")])
    result = parse_winehq_page(html)
    assert result == [(2, "WinZip"), (5, "Winamp"), (10, "Microsoft Word")]


def test_parse_empty_page_returns_empty_list():
    html = _make_list_page([])
    assert parse_winehq_page(html) == []


def test_parse_ignores_sidebar_browse_apps_link():
    html = (
        '<a href="./objectManager.php?sClass=application&amp;sTitle=Browse">Browse Apps</a>'
        + _make_list_page([(42, "Notepad++")])
    )
    # No iId= in the sidebar link, so only the table app is extracted
    result = parse_winehq_page(html)
    assert result == [(42, "Notepad++")]


def test_parse_strips_whitespace_from_names():
    html = _make_list_page([(99, "  Spaced App  ")])
    result = parse_winehq_page(html)
    assert result == [(99, "Spaced App")]


# ── ingest_winehq (mocked HTTP) ──────────────────────────────────────────────

@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_platinum_verdict_is_layer_excellent(MockSession, mock_sleep, db):
    page = _make_list_page([(1, "TestApp")])

    def mock_get(url, **_):
        return _mock_response(page)

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    row = db.execute("SELECT verdict FROM app WHERE app_id = 'winehq.1'").fetchone()
    assert row is not None
    # Platinum is the first tier processed, so this app gets layer_excellent
    assert row[0] == "layer_excellent"


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_silver_verdict_is_layer_workable(MockSession, mock_sleep, db):
    # Return no results for Platinum/Gold, one app for Silver, none for Bronze
    def mock_get(url, **_):
        if "ratingData0=Silver" in url:
            return _mock_response(_make_list_page([(7, "SilverApp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    row = db.execute("SELECT verdict FROM app WHERE app_id = 'winehq.7'").fetchone()
    assert row is not None
    assert row[0] == "layer_workable"


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_bronze_verdict_is_layer_poor(MockSession, mock_sleep, db):
    def mock_get(url, **_):
        if "ratingData0=Bronze" in url:
            return _mock_response(_make_list_page([(3, "BronzeApp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    row = db.execute("SELECT verdict FROM app WHERE app_id = 'winehq.3'").fetchone()
    assert row is not None
    assert row[0] == "layer_poor"


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_better_tier_wins_when_app_appears_in_multiple_tiers(MockSession, mock_sleep, db):
    """App 42 appears in both Platinum and Silver; Platinum is processed first
    via INSERT OR IGNORE, so it must end up with layer_excellent."""
    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(42, "CrossTierApp")]))
        if "ratingData0=Silver" in url:
            return _mock_response(_make_list_page([(42, "CrossTierApp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    row = db.execute("SELECT verdict FROM app WHERE app_id = 'winehq.42'").fetchone()
    assert row is not None
    assert row[0] == "layer_excellent"


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_creates_alias(MockSession, mock_sleep, db):
    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(10, "Microsoft Word")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    row = db.execute(
        "SELECT app_id, source FROM app_alias WHERE alias_norm = 'microsoft word'"
    ).fetchone()
    assert row == ("winehq.10", "upstream")


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_does_not_overwrite_curated_app(MockSession, mock_sleep, db):
    """A pre-seeded app row (e.g. from curated YAML) must not be overwritten."""
    db.execute(
        "INSERT INTO app VALUES "
        "('winehq.17','Adobe Photoshop',NULL,'creative','replace','high',0,NULL,date('now'))"
    )
    db.commit()

    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(17, "Adobe Photoshop")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    apps = ingest_winehq(db, delay=0)

    assert apps == 0  # no new rows
    verdict = db.execute(
        "SELECT verdict FROM app WHERE app_id = 'winehq.17'"
    ).fetchone()[0]
    assert verdict == "replace"  # curated value preserved


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_returns_correct_count(MockSession, mock_sleep, db):
    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(1, "App A"), (2, "App B")]))
        if "ratingData0=Gold" in url:
            # App 2 already inserted from Platinum; App 3 is new
            return _mock_response(_make_list_page([(2, "App B"), (3, "App C")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    count = ingest_winehq(db, delay=0)

    assert count == 3  # A, B from Platinum; C from Gold (B already existed)


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_processes_multiple_pages(MockSession, mock_sleep, db):
    """Two pages of Platinum results must both be fetched and inserted."""
    page1_html = _make_list_page([(1, "App One")], total_pages=2)
    page2_html = _make_list_page([(2, "App Two")], total_pages=2)

    call_count = {"n": 0}

    def mock_get(url, **_):
        if "ratingData0=Platinum" not in url:
            return _mock_response(_make_list_page([]))
        call_count["n"] += 1
        if "iPage=1" in url:
            return _mock_response(page1_html)
        if "iPage=2" in url:
            return _mock_response(page2_html)
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    count = ingest_winehq(db, delay=0)

    assert count == 2
    assert db.execute("SELECT COUNT(*) FROM app WHERE verdict='layer_excellent'").fetchone()[0] == 2


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_stores_notes_with_rating_label(MockSession, mock_sleep, db):
    """Notes field must include rating tier name so UI can surface it as evidence."""
    def mock_get(url, **_):
        if "ratingData0=Gold" in url:
            return _mock_response(_make_list_page([(5, "Winamp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    notes = db.execute("SELECT notes FROM app WHERE app_id = 'winehq.5'").fetchone()[0]
    assert notes is not None
    assert "Gold" in notes
    assert "Wine" in notes


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_confidence_is_medium(MockSession, mock_sleep, db):
    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(99, "SomeApp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    confidence = db.execute(
        "SELECT confidence FROM app WHERE app_id = 'winehq.99'"
    ).fetchone()[0]
    assert confidence == "medium"


@patch("harvester.sources.winehq.time.sleep")
@patch("harvester.sources.winehq.requests.Session")
def test_ingest_linux_native_is_zero(MockSession, mock_sleep, db):
    """WineHQ apps run via Wine, not natively — linux_native must be 0."""
    def mock_get(url, **_):
        if "ratingData0=Platinum" in url:
            return _mock_response(_make_list_page([(9, "WineApp")]))
        return _mock_response(_make_list_page([]))

    MockSession.return_value.get.side_effect = mock_get

    ingest_winehq(db, delay=0)

    native = db.execute(
        "SELECT linux_native FROM app WHERE app_id = 'winehq.9'"
    ).fetchone()[0]
    assert native == 0
