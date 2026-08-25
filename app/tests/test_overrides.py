"""Tests for the user verdict override system."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.models import ScanItem
from linuxready.overrides import (
    apply_user_overrides,
    load_user_overrides,
    remove_user_override,
    save_user_override,
)


def _item(matched_id: str | None, verdict: str = "unknown") -> ScanItem:
    return ScanItem(
        source="registry_apps",
        raw_name="Test App",
        raw_keys={},
        matched_id=matched_id,
        verdict=verdict,
    )


# ── load_user_overrides ───────────────────────────────────────────────────────

def test_load_missing_file_returns_empty(tmp_path):
    result = load_user_overrides(tmp_path / "nonexistent.yaml")
    assert result == {}


def test_load_empty_file_returns_empty(tmp_path):
    f = tmp_path / "overrides.yaml"
    f.write_text("", encoding="utf-8")
    assert load_user_overrides(f) == {}


def test_load_reads_overrides(tmp_path):
    f = tmp_path / "overrides.yaml"
    f.write_text(
        "overrides:\n  adobe.photoshop:\n    verdict: layer_workable\n    note: Works\n",
        encoding="utf-8",
    )
    result = load_user_overrides(f)
    assert "adobe.photoshop" in result
    assert result["adobe.photoshop"]["verdict"] == "layer_workable"
    assert result["adobe.photoshop"]["note"] == "Works"


def test_load_ignores_non_dict_values(tmp_path):
    f = tmp_path / "overrides.yaml"
    f.write_text("overrides:\n  bad.entry: just_a_string\n", encoding="utf-8")
    result = load_user_overrides(f)
    assert result == {}


# ── apply_user_overrides ──────────────────────────────────────────────────────

def test_apply_patches_verdict():
    item = _item("adobe.photoshop", "replace")
    apply_user_overrides([item], {"adobe.photoshop": {"verdict": "layer_workable"}})
    assert item.verdict == "layer_workable"


def test_apply_inserts_override_tag_in_evidence():
    item = _item("adobe.photoshop", "replace")
    apply_user_overrides([item], {"adobe.photoshop": {"verdict": "native"}})
    assert item.evidence[0] == "[User override]"


def test_apply_includes_note_in_evidence():
    item = _item("adobe.photoshop", "replace")
    apply_user_overrides(
        [item], {"adobe.photoshop": {"verdict": "native", "note": "Works great"}}
    )
    assert "Works great" in item.evidence[0]


def test_apply_sets_is_blocker_when_blocked():
    item = _item("some.app", "native")
    apply_user_overrides([item], {"some.app": {"verdict": "blocked"}})
    assert item.verdict == "blocked"
    assert item.is_blocker


def test_apply_clears_is_blocker_when_unblocked():
    item = _item("some.app", "blocked")
    item.is_blocker = True
    apply_user_overrides([item], {"some.app": {"verdict": "native"}})
    assert not item.is_blocker


def test_apply_skips_invalid_verdict():
    item = _item("some.app", "native")
    apply_user_overrides([item], {"some.app": {"verdict": "nonsense"}})
    assert item.verdict == "native"


def test_apply_skips_unmatched_items():
    item = _item(None, "unknown")
    apply_user_overrides([item], {"some.app": {"verdict": "native"}})
    assert item.verdict == "unknown"


def test_apply_empty_overrides_is_noop():
    item = _item("some.app", "native")
    apply_user_overrides([item], {})
    assert item.verdict == "native"
    assert item.evidence == []


# ── save_user_override ────────────────────────────────────────────────────────

def test_save_creates_file(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("adobe.photoshop", "layer_workable", path=path)
    assert path.exists()


def test_save_writes_correct_verdict(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("adobe.photoshop", "layer_workable", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["overrides"]["adobe.photoshop"]["verdict"] == "layer_workable"


def test_save_writes_note(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("adobe.photoshop", "layer_workable", note="Works in Bottles", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["overrides"]["adobe.photoshop"]["note"] == "Works in Bottles"


def test_save_omits_empty_note(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("adobe.photoshop", "native", note="", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "note" not in data["overrides"]["adobe.photoshop"]


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "overrides.yaml"
    save_user_override("some.app", "native", path=path)
    assert path.exists()


def test_save_preserves_existing_entries(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("first.app", "native", path=path)
    save_user_override("second.app", "blocked", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "first.app" in data["overrides"]
    assert "second.app" in data["overrides"]


def test_save_updates_existing_entry(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("some.app", "native", path=path)
    save_user_override("some.app", "blocked", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["overrides"]["some.app"]["verdict"] == "blocked"


def test_save_rejects_invalid_verdict(tmp_path):
    path = tmp_path / "overrides.yaml"
    with pytest.raises(ValueError):
        save_user_override("some.app", "nonsense", path=path)


# ── remove_user_override ──────────────────────────────────────────────────────

def test_remove_deletes_entry(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("some.app", "native", path=path)
    removed = remove_user_override("some.app", path=path)
    assert removed is True
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "some.app" not in (data.get("overrides") or {})


def test_remove_returns_false_when_missing(tmp_path):
    path = tmp_path / "overrides.yaml"
    assert remove_user_override("nonexistent", path=path) is False


def test_remove_preserves_other_entries(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("keep.app", "native", path=path)
    save_user_override("remove.app", "blocked", path=path)
    remove_user_override("remove.app", path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "keep.app" in data["overrides"]


# ── round-trip ────────────────────────────────────────────────────────────────

def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "overrides.yaml"
    save_user_override("some.app", "layer_workable", note="Test note", path=path)
    loaded = load_user_overrides(path)
    assert loaded["some.app"]["verdict"] == "layer_workable"
    assert loaded["some.app"]["note"] == "Test note"
