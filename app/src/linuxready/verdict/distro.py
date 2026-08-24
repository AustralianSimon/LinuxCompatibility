"""
Distro recommendation engine.

Returns a ranked shortlist (2-3 entries) based on the user's hardware profile
and gaming library. Pure function — no I/O, fully testable.
"""
from ..models import DistroRec, ScanItem

_NVIDIA = "10DE"
_AMD    = "1002"


def _signals(items: list[ScanItem]) -> dict:
    hw    = [i for i in items if i.source == "hardware"]
    games = [i for i in items if i.source == "steam"]

    gpu_vendor = next(
        (i.raw_keys.get("vendor_id") for i in hw if i.raw_keys.get("class") == "gpu"),
        None,
    )
    hw_unknowns  = sum(1 for i in hw if i.verdict == "unknown")
    wifi_unknown = any(
        i.verdict == "unknown" and i.raw_keys.get("class") == "wifi" for i in hw
    )

    return {
        "game_count":      len(games),
        "gpu_vendor":      gpu_vendor,
        "hw_unknown_count": hw_unknowns,
        "wifi_unknown":    wifi_unknown,
    }


# ── per-distro scorers ───────────────────────────────────────────────────────

def _bazzite(s: dict) -> tuple[int, DistroRec]:
    score = 0
    reasons: list[str] = []

    if s["game_count"] > 5:
        score += 4
        reasons.append(f"Large Steam library ({s['game_count']} games) — Proton, Steam Deck patches, and gaming kernel pre-configured")
    elif s["game_count"] > 0:
        score += 2
        reasons.append("Steam games detected — ships with Proton and gaming patches out of the box")

    if s["gpu_vendor"] == _AMD:
        score += 2
        reasons.append("AMD GPU — best-in-class open-source Mesa drivers, excellent Proton performance")
    elif s["gpu_vendor"] == _NVIDIA:
        score += 1
        reasons.append("NVIDIA GPU — ships proprietary drivers pre-installed, no manual setup needed")

    if s["hw_unknown_count"] > 0:
        score += 1
        reasons.append("Ships a very recent kernel (Fedora base), improving support for newer hardware")

    return score, DistroRec(
        name="Bazzite",
        tagline="Gaming-first immutable Linux based on Fedora Atomic",
        reasons=reasons[:3],
        url="https://bazzite.gg",
    )


def _mint(s: dict) -> tuple[int, DistroRec]:
    score = 2  # Always a reasonable choice for Windows migrants
    reasons: list[str] = ["Familiar desktop environment (Cinnamon) — the closest feel to Windows 10"]

    if s["game_count"] == 0:
        score += 3
        reasons.append("No gaming library detected — stable LTS base is ideal for productivity and everyday use")
    elif s["game_count"] < 4:
        score += 1
        reasons.append("Light gaming library — works well with Proton via Steam on a stable base")

    if s["hw_unknown_count"] == 0:
        score += 2
        reasons.append("All detected hardware has known Linux support — conservative LTS kernel is fine")

    return score, DistroRec(
        name="Linux Mint Cinnamon",
        tagline="Windows-familiar, stable, and ideal for first-time Linux users",
        reasons=reasons[:3],
        url="https://linuxmint.com",
    )


def _ubuntu(s: dict) -> tuple[int, DistroRec]:
    score = 1  # Solid baseline — always reasonable
    reasons: list[str] = ["Largest community and documentation base — answers to almost every question already exist"]

    if s["game_count"] == 0:
        score += 2
        reasons.append("No gaming library — Ubuntu LTS is well-suited for general-purpose and office use")
    elif s["game_count"] < 6:
        score += 1

    if s["hw_unknown_count"] == 0:
        score += 1
        reasons.append("All detected hardware supported — Ubuntu's LTS kernel covers your setup")

    return score, DistroRec(
        name="Ubuntu LTS",
        tagline="The most widely-documented Linux — broadest software and hardware support",
        reasons=reasons[:3],
        url="https://ubuntu.com",
    )


def _fedora(s: dict) -> tuple[int, DistroRec]:
    score = 0
    reasons: list[str] = []

    if s["hw_unknown_count"] > 2:
        score += 4
        reasons.append(f"{s['hw_unknown_count']} hardware items not in our database — Fedora ships a very recent kernel, maximising new hardware support")
    elif s["hw_unknown_count"] > 0:
        score += 2
        reasons.append("Some hardware showing as unknown — Fedora's fresh kernel may provide better support")

    if s["wifi_unknown"]:
        score += 1
        reasons.append("Wi-Fi driver may need a newer kernel than Ubuntu LTS ships — Fedora is a safer choice")

    if s["game_count"] > 0:
        score += 1
        reasons.append("Ships Proton-ready and is the upstream base for gaming distros like Bazzite")

    if s["gpu_vendor"] in (_NVIDIA, _AMD):
        score += 1

    return score, DistroRec(
        name="Fedora Workstation",
        tagline="Fresh kernel and latest open-source software — best for new hardware",
        reasons=reasons[:3],
        url="https://fedoraproject.org",
    )


def _popos(s: dict) -> tuple[int, DistroRec]:
    score = 0
    reasons: list[str] = []

    if s["gpu_vendor"] == _NVIDIA:
        score += 4
        reasons.append("NVIDIA GPU — Pop!_OS ships NVIDIA drivers on the ISO itself, eliminating the most common first-boot headache")

    if s["game_count"] > 0:
        score += 1
        reasons.append("Gaming-friendly Ubuntu base — full Steam and Proton support with a polished GNOME desktop")

    if s["hw_unknown_count"] > 0:
        score += 1
        reasons.append("Offers an LTS-kernel and a newer HWE kernel option at install time")

    return score, DistroRec(
        name="Pop!_OS",
        tagline="Ubuntu-based with best-in-class NVIDIA driver support",
        reasons=reasons[:3],
        url="https://pop.system76.com",
    )


# ── public API ───────────────────────────────────────────────────────────────

def recommend_distros(items: list[ScanItem]) -> list[DistroRec]:
    """
    Return 2–3 ranked distro recommendations based on the scan results.
    Always returns at least 2 entries.
    """
    s = _signals(items)

    scored = sorted(
        [_bazzite(s), _mint(s), _ubuntu(s), _fedora(s), _popos(s)],
        key=lambda x: x[0],
        reverse=True,
    )

    # Take distros with a positive score; guarantee at least 2
    recs = [rec for score, rec in scored if score > 0]
    if len(recs) < 2:
        recs = [rec for _, rec in scored[:2]]

    return recs[:3]
