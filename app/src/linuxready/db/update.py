import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from ..config import DB_PATH, GITHUB_REPO

_HARVESTER_DIR = Path(__file__).parent.parent.parent.parent.parent / "harvester"


def download_db(
    repo: str = GITHUB_REPO,
    dest: Path = DB_PATH,
    progress_cb: Callable[[str], None] | None = None,
) -> None:
    """Download compat.db from the latest GitHub release and atomically replace dest."""

    def _log(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    _log("Checking latest release…")
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("No releases found in the GitHub repository.")
        raise RuntimeError(f"GitHub API error: {e.code} {e.reason}")

    assets = release.get("assets", [])
    asset = next((a for a in assets if a["name"] == "compat.db"), None)
    if asset is None:
        raise RuntimeError("No compat.db asset found in the latest release.")

    tag = release.get("tag_name", "?")
    size_kb = asset.get("size", 0) // 1024
    _log(f"Found release {tag} — compat.db ({size_kb:,} KB). Downloading…")

    download_url = asset["browser_download_url"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".db.tmp")
    try:
        urllib.request.urlretrieve(download_url, tmp)
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    _log("Download complete.")


def run_harvester(
    dest: Path = DB_PATH,
    harvester_dir: Path = _HARVESTER_DIR,
    progress_cb: Callable[[str], None] | None = None,
) -> None:
    """Run the harvester locally and atomically replace dest with the result."""

    def _log(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    if not harvester_dir.is_dir():
        raise RuntimeError(f"Harvester directory not found: {harvester_dir}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()

    _log(f"Running harvester in {harvester_dir}…")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    cmd = ["uv", "run", "harvest", "--output", str(tmp)]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(harvester_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        raise RuntimeError("'uv' not found in PATH — install uv to run the harvester locally.")

    assert proc.stdout
    for line in proc.stdout:
        _log(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Harvester exited with code {proc.returncode}.")

    if not tmp.exists():
        raise RuntimeError("Harvester finished but no output file was produced.")

    os.replace(tmp, dest)
    _log("Database updated successfully.")
