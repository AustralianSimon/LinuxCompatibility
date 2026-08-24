"""
Name normalisation — mirrors app/src/linuxready/matcher/normalize.py exactly.
Must stay in sync so game_alias.alias_norm values match what the app resolver produces.
"""
import re

_TRANSFORMS = [
    (re.compile(r"[®©™]"), ""),
    (re.compile(r"\s+v?\d+[\.\d]*\s*$", re.I), ""),
    (re.compile(r"\s+\(?\s*(?:x64|x86|64-bit|32-bit|arm64)\s*\)?", re.I), ""),
    (re.compile(r"\s+\(\d{4}\)\s*$"), ""),
    (re.compile(r"[^\w\s]"), " "),
]
_COLLAPSE = re.compile(r"\s+")


def normalize(name: str) -> str:
    n = name.strip()
    for pattern, repl in _TRANSFORMS:
        n = pattern.sub(repl, n)
    return _COLLAPSE.sub(" ", n).lower().strip()
