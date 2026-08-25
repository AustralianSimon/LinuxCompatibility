"""
Generate a post-install bash script from a scan result.

Parses ScanItem.actions for entries in the form '[ecosystem] <command>'
(written by verdict/rules.py when app_package rows carry install_hint values)
and groups them into a runnable shell script the user can copy to their
new Linux installation.
"""
import re
from ..models import ScanResult

_ACTION_RE = re.compile(r"^\[(\w+)\]\s+(.+)$")
_KNOWN_ECOSYSTEMS = {"flatpak", "apt", "snap", "dnf", "pacman", "yum", "zypper"}

_SECTION_HEADERS = {
    "flatpak": "# ── Flatpak ──────────────────────────────────────────────────────────────",
    "apt":     "# ── apt  (Debian / Ubuntu / Mint) ───────────────────────────────────────",
    "snap":    "# ── Snap ─────────────────────────────────────────────────────────────────",
    "dnf":     "# ── dnf  (Fedora / RHEL) ────────────────────────────────────────────────",
    "pacman":  "# ── pacman  (Arch / Manjaro) ────────────────────────────────────────────",
    "zypper":  "# ── zypper  (openSUSE) ──────────────────────────────────────────────────",
}

_SKIP_VERDICTS = frozenset({"blocked", "unknown", "replace", "layer_poor", None})
_FLATPAK_REMOTE = (
    "flatpak remote-add --if-not-exists flathub "
    "https://dl.flathub.org/repo/flathub.flatpakrepo"
)


def generate_install_script(result: ScanResult) -> str:
    """Return a bash script string that installs Linux equivalents of scanned apps."""
    groups: dict[str, list[tuple[str, str]]] = {}

    for item in result.items:
        if item.verdict in _SKIP_VERDICTS:
            continue
        for action in item.actions:
            m = _ACTION_RE.match(action)
            if not m:
                continue
            eco = m.group(1).lower()
            cmd = m.group(2).strip()
            if eco not in _KNOWN_ECOSYSTEMS:
                continue
            groups.setdefault(eco, []).append((item.raw_name, cmd))

    header = [
        "#!/usr/bin/env bash",
        "# LinuxReadyAmI — post-install script",
        f"# Scan: {result.scan_id[:8]}  |  DB: {result.db_build}",
        "# Run on your new Linux install to set up your apps.",
        "",
    ]

    if not groups:
        return "\n".join(header + [
            "# No Linux packages were identified for the apps in this scan.",
        ]) + "\n"

    lines = header + ["set -euo pipefail", ""]

    if "flatpak" in groups:
        lines += [
            "# Add Flathub remote (safe to run more than once)",
            _FLATPAK_REMOTE,
            "",
        ]

    for eco in ("flatpak", "apt", "snap", "dnf", "pacman", "zypper", "yum"):
        entries = groups.get(eco)
        if not entries:
            continue
        lines.append(_SECTION_HEADERS.get(eco, f"# ── {eco} ──"))
        for app_name, cmd in entries:
            lines.append(f"# {app_name}")
            lines.append(cmd)
        lines.append("")

    return "\n".join(lines)
