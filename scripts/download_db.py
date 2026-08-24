#!/usr/bin/env python3
"""
Download the latest compat.db from GitHub Releases.

Usage:
    python scripts/download_db.py
    python scripts/download_db.py --output path/to/compat.db
    python scripts/download_db.py --repo owner/name  # override repo
"""
import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

GITHUB_REPO = "AustralianSimon/LinuxCompatibility"
ASSET_NAME  = "compat.db"
DEFAULT_OUT = Path(__file__).parent.parent / "app" / "src" / "linuxready" / "db" / "compat.db"

API_URL  = "https://api.github.com/repos/{repo}/releases/latest"
HEADERS  = {"Accept": "application/vnd.github+json", "User-Agent": "linuxready-download-script"}


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    bar = "#" * int(pct / 2)
                    print(f"\r  [{bar:<50}] {pct:.0f}%", end="", flush=True)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download latest compat.db from GitHub Releases")
    parser.add_argument("--output", metavar="FILE", type=Path, default=DEFAULT_OUT,
                        help=f"Destination path (default: {DEFAULT_OUT})")
    parser.add_argument("--repo", metavar="OWNER/NAME", default=GITHUB_REPO,
                        help=f"GitHub repo (default: {GITHUB_REPO})")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt when overwriting an existing file")
    args = parser.parse_args()

    print(f"Fetching latest release from github.com/{args.repo} ...")
    try:
        release = _fetch_json(API_URL.format(repo=args.repo))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"ERROR: No releases found for {args.repo}.", file=sys.stderr)
            print("       Run the harvester first and publish a release with compat.db attached.",
                  file=sys.stderr)
        else:
            print(f"ERROR: GitHub API returned {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    tag = release.get("tag_name", "unknown")
    published = release.get("published_at", "")[:10]
    assets = release.get("assets", [])

    asset = next((a for a in assets if a["name"] == ASSET_NAME), None)
    if asset is None:
        names = [a["name"] for a in assets]
        print(f"ERROR: Release {tag} has no asset named '{ASSET_NAME}'.", file=sys.stderr)
        print(f"       Assets found: {names or '(none)'}", file=sys.stderr)
        sys.exit(1)

    size_mb = asset["size"] / 1_048_576
    print(f"Found: {ASSET_NAME}  ({size_mb:.1f} MB)  release {tag}  published {published}")

    if args.output.exists() and not args.yes:
        answer = input(f"Overwrite existing {args.output}? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    tmp = args.output.with_suffix(".db.tmp")
    try:
        print(f"Downloading to {args.output} ...")
        _download(asset["browser_download_url"], tmp)
        shutil.move(tmp, args.output)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. compat.db written to {args.output}")
    print(f"Run: python -m linuxready  (or linuxready --gui)")


if __name__ == "__main__":
    main()
