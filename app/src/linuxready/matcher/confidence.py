_TIER_CONFIDENCE = {
    1: "exact",
    2: "exact",
    3: "high",
    4: "medium",
    5: "low",
    6: "unknown",
}


def tier_confidence(tier: int) -> str:
    return _TIER_CONFIDENCE.get(tier, "unknown")
