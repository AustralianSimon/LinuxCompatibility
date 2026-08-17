from ..config import READINESS_WEIGHTS, VERDICTS_PASS, VERDICTS_PARTIAL
from ..models import ScanItem


def compute_score(items: list[ScanItem]) -> dict:
    apps  = [i for i in items if i.source == "registry_apps"]
    games = [i for i in items if i.source == "steam"]
    hw    = [i for i in items if i.source in ("hardware", "firmware")]

    hard_blockers = sum(1 for i in items if i.is_blocker)
    unknown_count = sum(1 for i in items if i.verdict == "unknown")

    hw_rate   = _pass_rate(hw)
    app_rate  = _pass_rate(apps)
    game_rate = _pass_rate(games)

    w = READINESS_WEIGHTS
    base = hw_rate * w["hw"] + app_rate * w["apps"] + game_rate * w["games"]

    # Each hard blocker cuts the score; floor at 0.30 so the number remains readable
    penalty = max(0.30, 1.0 - hard_blockers * 0.15)
    value = max(0, min(100, int(round(base * penalty * 100))))

    return {"value": value, "hard_blockers": hard_blockers, "unknown_count": unknown_count}


def _pass_rate(group: list[ScanItem]) -> float:
    known = [i for i in group if i.verdict and i.verdict != "unknown"]
    if not known:
        return 1.0  # no data → no penalty
    passes = sum(1.0 if i.verdict in VERDICTS_PASS else
                 0.5 if i.verdict in VERDICTS_PARTIAL else 0.0
                 for i in known)
    return passes / len(known)
