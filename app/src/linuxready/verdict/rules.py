import sqlite3

from ..models import ScanItem

_ANTICHEAT_BLOCKED = frozenset({"kernel_blocked", "denied", "broken"})
_PROTON_EXCELLENT  = frozenset({"platinum", "gold"})
_PROTON_WORKABLE   = frozenset({"silver"})
_PROTON_POOR       = frozenset({"bronze"})

_SUPPORT_TO_VERDICT = {
    "excellent":   "native",
    "good":        "native",
    "needs_setup": "layer_workable",
    "poor":        "layer_poor",
    "unsupported": "blocked",
}


def assign_verdict(item: ScanItem, conn: sqlite3.Connection) -> ScanItem:
    """Populate verdict, is_blocker, evidence, and actions on item. Returns item."""
    # Firmware and hardware are assessed from raw_keys — no name match needed.
    if item.source == "firmware":
        _firmware_verdict(item)
        return item

    if item.source == "hardware":
        _hardware_verdict(item, conn)
        return item

    if item.matched_id is None:
        item.verdict = "unknown"
        return item

    if item.source in ("steam", "epic", "gog", "xbox"):
        _game_verdict(item, conn)
    elif item.source in ("registry_apps", "msix"):
        _app_verdict(item, conn)
    else:
        item.verdict = "unknown"

    return item


def _game_verdict(item: ScanItem, conn: sqlite3.Connection) -> None:
    # matched_id is the steam_appid (as str) for all game sources
    appid = item.matched_id
    if appid is None:
        item.verdict = "unknown"
        return

    row = conn.execute(
        "SELECT native_linux, deck_verified, proton_tier, proton_sample, anticheat, notes "
        "FROM game WHERE steam_appid = ?",
        (int(appid),),
    ).fetchone()
    if not row:
        item.verdict = "unknown"
        return

    native, deck, proton_tier, sample, anticheat, notes = row

    if anticheat in _ANTICHEAT_BLOCKED:
        item.verdict = "blocked"
        item.is_blocker = True
        if anticheat == "denied":
            item.evidence.append("Anticheat actively denies Linux (AreWeAntiCheatYet: Denied)")
        elif anticheat == "broken":
            item.evidence.append("Anticheat broken on Linux (AreWeAntiCheatYet: Broken)")
        else:
            item.evidence.append("Kernel-level anticheat blocks Linux play")
        if notes:
            item.evidence.append(notes)
        return

    if native:
        item.verdict = "native"
        item.evidence.append("Native Linux build on Steam")
        if deck:
            item.evidence.append(f"Steam Deck: {deck}")
        return

    if proton_tier in _PROTON_EXCELLENT:
        item.verdict = "layer_excellent"
    elif proton_tier in _PROTON_WORKABLE:
        item.verdict = "layer_workable"
    elif proton_tier in _PROTON_POOR:
        item.verdict = "layer_poor"
    else:
        item.verdict = "unknown"

    if proton_tier:
        sample_note = f" ({sample:,} reports)" if sample else ""
        item.evidence.append(f"ProtonDB: {proton_tier.capitalize()}{sample_note}")
    if deck:
        item.evidence.append(f"Steam Deck: {deck}")
    if anticheat == "supported":
        item.evidence.append("Anticheat: Linux officially supported (AreWeAntiCheatYet)")
    elif anticheat == "running":
        item.evidence.append("Anticheat: reported working, not officially supported")
    elif anticheat and anticheat not in ("none", "unknown"):
        item.evidence.append(f"Anticheat: {anticheat.replace('_', ' ')}")
    if notes:
        item.evidence.append(notes)

    item.actions.append("Enable Proton in Steam › Settings › Compatibility")


def _app_verdict(item: ScanItem, conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT verdict, linux_native, notes FROM app WHERE app_id = ?",
        (item.matched_id,),
    ).fetchone()
    if not row:
        item.verdict = "unknown"
        return

    verdict, _native, notes = row
    item.verdict = verdict
    if notes:
        item.evidence.append(notes)
    if verdict == "blocked":
        item.is_blocker = True

    pkgs = conn.execute(
        "SELECT ecosystem, install_hint FROM app_package WHERE app_id = ?",
        (item.matched_id,),
    ).fetchall()
    for eco, hint in pkgs:
        if hint:
            item.actions.append(f"[{eco}] {hint}")

    if verdict == "replace":
        alts = conn.execute(
            "SELECT alt_name, rationale, caveat FROM app_alternative "
            "WHERE app_id = ? ORDER BY rank",
            (item.matched_id,),
        ).fetchall()
        for alt_name, rationale, caveat in alts:
            note = f"Alternative: {alt_name}"
            if rationale:
                note += f" — {rationale}"
            if caveat:
                note += f" (note: {caveat})"
            item.evidence.append(note)


def _hardware_verdict(item: ScanItem, conn: sqlite3.Connection) -> None:
    ven = item.raw_keys.get("vendor_id")
    dev = item.raw_keys.get("device_id")
    cls = item.raw_keys.get("class")
    if not ven:
        item.verdict = "unknown"
        return

    # Exact vendor+device first, then vendor-only fallback (device_id IS NULL)
    row = conn.execute(
        "SELECT support, driver, min_kernel, notes FROM hardware "
        "WHERE vendor_id = ? AND (device_id = ? OR device_id IS NULL) AND class = ? "
        "ORDER BY CASE WHEN device_id IS NULL THEN 1 ELSE 0 END LIMIT 1",
        (ven, dev, cls),
    ).fetchone()
    if not row:
        item.verdict = "unknown"
        return

    support, driver, min_kernel, notes = row
    item.verdict = _SUPPORT_TO_VERDICT.get(support, "unknown")

    if driver:
        item.evidence.append(f"Driver: {driver}")
    if min_kernel:
        item.evidence.append(f"Requires kernel ≥ {min_kernel}")
    if notes:
        item.evidence.append(notes)

    if item.verdict == "blocked":
        item.is_blocker = True
    if item.verdict == "needs_setup":
        item.verdict = "layer_workable"  # map to user-visible verdict


def _firmware_verdict(item: ScanItem) -> None:
    keys = item.raw_keys
    item.verdict = "native"  # default — no match needed, assessed directly

    storage = keys.get("storage_mode") or ""
    if "RST" in storage or "RAID" in storage:
        item.verdict = "blocked"
        item.is_blocker = True
        item.evidence.append(
            "Storage controller in RST/RAID mode — Linux installers cannot see the disk. "
            "Switch to AHCI in BIOS/UEFI firmware settings before installing Linux."
        )

    bitlocker = (keys.get("bitlocker") or "").lower()
    if bitlocker in ("on", "protectionon"):
        item.evidence.append(
            "BitLocker is active — suspend or disable BitLocker before repartitioning "
            "(Control Panel › BitLocker Drive Encryption › Suspend)."
        )

    disk_style = (keys.get("disk_style") or "").upper()
    if disk_style == "MBR":
        item.evidence.append(
            "Disk uses MBR partition style (max 4 primary partitions). "
            "GPT is strongly preferred for dual-boot."
        )

    free_gb = keys.get("free_gb")
    if free_gb is not None and free_gb < 30:
        item.verdict = "blocked"
        item.is_blocker = True
        item.evidence.append(
            f"Only {free_gb:.1f} GB free on system drive — "
            "Linux requires at least 25–30 GB for a usable installation."
        )
