"""
Tests for db/update.py — mocks network and subprocess calls.
Note: subprocess Unicode output (✓, …) is NOT exercised by these mocks;
see update.py for the encoding fix (PYTHONIOENCODING=utf-8, errors=replace).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linuxready.db.update import download_db, run_harvester

# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_release(tag: str = "v1.0", asset_name: str = "compat.db",
                  size: int = 1024 * 512) -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": asset_name,
                "size": size,
                "browser_download_url": f"https://example.com/releases/{tag}/{asset_name}",
            }
        ],
    }


def _urlopen_returning(data: dict):
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── download_db ───────────────────────────────────────────────────────────────

def test_download_db_success(tmp_path):
    dest = tmp_path / "compat.db"
    release = _fake_release()

    with (
        patch("urllib.request.urlopen", return_value=_urlopen_returning(release)),
        patch("urllib.request.urlretrieve") as mock_retrieve,
        patch("os.replace") as mock_replace,
    ):
        def _fake_retrieve(url, path):
            Path(path).write_bytes(b"FAKE_DB")

        mock_retrieve.side_effect = _fake_retrieve
        download_db(dest=dest)

    mock_replace.assert_called_once()
    args = mock_replace.call_args[0]
    assert args[1] == dest


def test_download_db_calls_progress_cb(tmp_path):
    dest = tmp_path / "compat.db"
    logs: list[str] = []

    with (
        patch("urllib.request.urlopen", return_value=_urlopen_returning(_fake_release())),
        patch("urllib.request.urlretrieve", side_effect=lambda url, p: Path(p).write_bytes(b"")),
        patch("os.replace"),
    ):
        download_db(dest=dest, progress_cb=logs.append)

    assert any("Checking" in m for m in logs)
    assert any("Found release" in m for m in logs)
    assert any("Download complete" in m for m in logs)


def test_download_db_404_raises_runtime_error(tmp_path):
    dest = tmp_path / "compat.db"
    err = urllib.error.HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="No releases found"):
            download_db(dest=dest)


def test_download_db_other_http_error_raises(tmp_path):
    dest = tmp_path / "compat.db"
    err = urllib.error.HTTPError(url="", code=500, msg="Server Error", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="500"):
            download_db(dest=dest)


def test_download_db_no_asset_raises(tmp_path):
    dest = tmp_path / "compat.db"
    release = {"tag_name": "v1.0", "assets": [{"name": "README.md", "size": 100,
                                                "browser_download_url": "http://x"}]}

    with patch("urllib.request.urlopen", return_value=_urlopen_returning(release)):
        with pytest.raises(RuntimeError, match="No compat.db asset"):
            download_db(dest=dest)


def test_download_db_cleans_up_tmp_on_retrieve_error(tmp_path):
    dest = tmp_path / "compat.db"
    tmp = dest.with_suffix(".db.tmp")

    def _failing_retrieve(url, path):
        Path(path).write_bytes(b"partial")
        raise OSError("network dropped")

    with (
        patch("urllib.request.urlopen", return_value=_urlopen_returning(_fake_release())),
        patch("urllib.request.urlretrieve", side_effect=_failing_retrieve),
    ):
        with pytest.raises(OSError):
            download_db(dest=dest)

    assert not tmp.exists()


# ── run_harvester ─────────────────────────────────────────────────────────────

def _fake_proc(returncode: int = 0, output: str = "done\n"):
    proc = MagicMock()
    proc.stdout = iter(output.splitlines(keepends=True))
    proc.returncode = returncode
    proc.wait.return_value = None
    return proc


def test_run_harvester_dir_not_found(tmp_path):
    with pytest.raises(RuntimeError, match="Harvester directory not found"):
        run_harvester(dest=tmp_path / "out.db", harvester_dir=tmp_path / "no_such_dir")


def test_run_harvester_uv_not_found(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()

    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="'uv' not found"):
            run_harvester(dest=tmp_path / "out.db", harvester_dir=harvester_dir)


def test_run_harvester_nonzero_exit(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()

    with patch("subprocess.Popen", return_value=_fake_proc(returncode=1)):
        with pytest.raises(RuntimeError, match="exited with code 1"):
            run_harvester(dest=tmp_path / "out.db", harvester_dir=harvester_dir)


def test_run_harvester_no_output_file(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()

    with patch("subprocess.Popen", return_value=_fake_proc(returncode=0, output="")):
        with pytest.raises(RuntimeError, match="no output file"):
            run_harvester(dest=tmp_path / "out.db", harvester_dir=harvester_dir)


def test_run_harvester_success(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()
    dest = tmp_path / "compat.db"

    def _fake_popen(cmd, **kwargs):
        # Simulate the harvester writing to --output path
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.write_bytes(b"FAKE_DB_CONTENT")
        return _fake_proc(returncode=0, output="[1/6] step one\n  [1/6] step one  ✓\n")

    with patch("subprocess.Popen", side_effect=_fake_popen):
        run_harvester(dest=dest, harvester_dir=harvester_dir)

    assert dest.exists()
    assert dest.read_bytes() == b"FAKE_DB_CONTENT"


def test_run_harvester_streams_output_to_progress_cb(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()
    dest = tmp_path / "compat.db"
    logs: list[str] = []

    def _fake_popen(cmd, **kwargs):
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.write_bytes(b"DB")
        return _fake_proc(returncode=0, output="line one\nline two\n")

    with patch("subprocess.Popen", side_effect=_fake_popen):
        run_harvester(dest=dest, harvester_dir=harvester_dir, progress_cb=logs.append)

    assert "line one" in logs
    assert "line two" in logs
    assert any("updated successfully" in m for m in logs)


def test_run_harvester_passes_utf8_env(tmp_path):
    harvester_dir = tmp_path / "harvester"
    harvester_dir.mkdir()
    captured_env: dict = {}

    def _capture_popen(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.write_bytes(b"DB")
        return _fake_proc()

    with patch("subprocess.Popen", side_effect=_capture_popen):
        run_harvester(dest=tmp_path / "compat.db", harvester_dir=harvester_dir)

    assert captured_env.get("PYTHONIOENCODING") == "utf-8"
    assert captured_env.get("PYTHONUTF8") == "1"
