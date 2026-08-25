"""Tests for the distro recommendation engine."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.models import ScanItem
from linuxready.verdict.distro import recommend_distros


def _hw(cls: str, vendor: str, verdict: str = "native") -> ScanItem:
    return ScanItem(source="hardware", raw_name=cls,
                    raw_keys={"class": cls, "vendor_id": vendor}, verdict=verdict)

def _game(name: str = "Game") -> ScanItem:
    return ScanItem(source="steam", raw_name=name, raw_keys={}, verdict="layer_excellent")

def _app(name: str = "App") -> ScanItem:
    return ScanItem(source="registry_apps", raw_name=name, raw_keys={}, verdict="native")


# ── always returns 2-3 results ───────────────────────────────────────────────

def test_always_returns_at_least_two():
    recs = recommend_distros([])
    assert len(recs) >= 2

def test_never_returns_more_than_three():
    items = [_game() for _ in range(20)] + [_hw("gpu", "1002")]
    recs = recommend_distros(items)
    assert len(recs) <= 3

def test_all_recs_have_required_fields():
    for rec in recommend_distros([]):
        assert rec.name
        assert rec.tagline
        assert rec.url.startswith("https://")
        assert isinstance(rec.reasons, list)


# ── gaming profile → Bazzite first ──────────────────────────────────────────

def test_heavy_gamer_amd_gets_bazzite_first():
    items = [_game(f"Game {i}") for i in range(10)] + [_hw("gpu", "1002")]
    recs = recommend_distros(items)
    assert recs[0].name == "Bazzite"

def test_heavy_gamer_nvidia_gets_bazzite_or_popos_first():
    items = [_game(f"Game {i}") for i in range(10)] + [_hw("gpu", "10DE")]
    recs = recommend_distros(items)
    assert recs[0].name in ("Bazzite", "Pop!_OS")


# ── NVIDIA without gaming → Pop!_OS appears in recommendations ──────────────

def test_nvidia_no_games_includes_popos():
    items = [_hw("gpu", "10DE")]
    recs = recommend_distros(items)
    names = [r.name for r in recs]
    assert "Pop!_OS" in names


# ── no games, known hardware → Mint or Ubuntu first ─────────────────────────

def test_no_games_known_hw_gets_mint_or_ubuntu_first():
    items = [_hw("gpu", "8086", verdict="native"), _app()]
    recs = recommend_distros(items)
    assert recs[0].name in ("Linux Mint Cinnamon", "Ubuntu LTS")


# ── many hardware unknowns → Fedora in top 2 ────────────────────────────────

def test_new_hardware_includes_fedora():
    items = [_hw("gpu", "10DE", verdict="unknown"),
             _hw("wifi", "8086", verdict="unknown"),
             _hw("storage", "144D", verdict="unknown")]
    recs = recommend_distros(items)
    names = [r.name for r in recs]
    assert "Fedora Workstation" in names


# ── reasons are generated ───────────────────────────────────────────────────

def test_bazzite_reasons_mention_game_count():
    items = [_game(f"G{i}") for i in range(8)] + [_hw("gpu", "1002")]
    recs = recommend_distros(items)
    bazzite = next(r for r in recs if r.name == "Bazzite")
    assert any("8" in reason or "game" in reason.lower() for reason in bazzite.reasons)
