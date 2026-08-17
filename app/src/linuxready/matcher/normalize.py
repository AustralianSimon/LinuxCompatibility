import re

# Patterns applied in order before final whitespace collapse
_TRANSFORMS = [
    (re.compile(r"[®©™]"), ""),                         # ®©™
    (re.compile(r"\s+v?\d+[\.\d]*\s*$", re.I), ""),                   # trailing version
    (re.compile(r"\s+\(?\s*(?:x64|x86|64-bit|32-bit|arm64)\s*\)?", re.I), ""),  # arch
    (re.compile(r"\s+\(\d{4}\)\s*$"), ""),                             # (year)
    (re.compile(r"[^\w\s]"), " "),                                     # non-word chars → space
]
_COLLAPSE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """
    Canonical form used for alias lookups and fuzzy matching.
    Strips version noise, arch tags, punctuation; lowercases; collapses whitespace.
    """
    n = name.strip()
    for pattern, repl in _TRANSFORMS:
        n = pattern.sub(repl, n)
    return _COLLAPSE.sub(" ", n).lower().strip()
