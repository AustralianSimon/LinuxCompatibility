"""Tests for the bad_match_url helper."""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.matcher.resolver import bad_match_url
from linuxready.models import ScanItem


def _item(**kwargs) -> ScanItem:
    defaults = dict(source="registry_apps", raw_name="Test App", raw_keys={},
                    matched_id="test.app", match_tier=2, match_confidence="exact")
    return ScanItem(**{**defaults, **kwargs})


def test_url_structure():
    url = bad_match_url(_item(), "2026-08-14")
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path.endswith("/issues/new")


def test_url_contains_required_params():
    url = bad_match_url(_item(raw_name='Adobe Photoshop', matched_id='adobe.photoshop',
                               match_tier=2, match_confidence='exact'), "2026-08-14")
    qs = parse_qs(urlparse(url).query)
    assert qs["labels"] == ["bad-match"]
    assert qs["template"] == ["bad-match.yml"]
    assert "Adobe Photoshop" in qs["title"][0]
    assert qs["app_id"] == ["adobe.photoshop"]
    assert qs["match_tier"] == ["2"]
    assert qs["confidence"] == ["exact"]
    assert qs["db_build"] == ["2026-08-14"]
    assert "app_version" in qs


def test_unmatched_item_uses_none():
    url = bad_match_url(_item(matched_id=None, match_tier=None, match_confidence="unknown"),
                         "2026-08-14")
    qs = parse_qs(urlparse(url).query)
    assert qs["app_id"] == ["none"]
    assert qs["match_tier"] == ["none"]


def test_no_machine_identifying_fields():
    item = _item(raw_name="Firefox", raw_keys={"publisher": "Mozilla", "version": "130.0"})
    url = bad_match_url(item, "2026-08-14")
    # raw_keys values must not appear in the URL
    assert "Mozilla" not in url
    assert "130.0" not in url
