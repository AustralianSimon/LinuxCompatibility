import argparse
import dataclasses
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import APP_NAME, DB_PATH, SCANS_DIR, SCHEMA_VERSION
from .collectors.epic import EpicCollector
from .collectors.gog import GogCollector
from .collectors.hardware import HardwareCollector
from .collectors.msix import MsixCollector
from .collectors.registry_apps import RegistryAppsCollector
from .collectors.steam import SteamCollector
from .collectors.userdata import UserdataCollector
from .collectors.xbox import XboxCollector
from .db.access import get_meta, open_db
from .matcher.resolver import resolve
from .models import ScanContext, ScanResult
from .overrides import apply_user_overrides, load_user_overrides
from .report.install_script import generate_install_script
from .report.render import render_report
from .verdict.distro import recommend_distros
from .verdict.rules import assign_verdict
from .verdict.score import compute_score


def run_scan(db_path: Path | None = None,
             progress_cb=None) -> ScanResult:
    """
    Run a full scan and return a ScanResult.
    progress_cb(collector_id: str, status: str) — optional progress hook for the GUI.
    """
    db_path = db_path or DB_PATH
    ctx = ScanContext(db_path=str(db_path))

    collectors = [
        SteamCollector(), EpicCollector(), GogCollector(), XboxCollector(),
        RegistryAppsCollector(), MsixCollector(), HardwareCollector(),
        UserdataCollector(),
    ]
    all_raw_items = []
    all_migration = []
    collector_summaries = []

    for c in collectors:
        if not c.available():
            collector_summaries.append(
                {"id": c.id, "status": "skipped", "duration_ms": 0, "warnings": []}
            )
            if progress_cb:
                progress_cb(c.id, "skipped")
            continue

        if progress_cb:
            progress_cb(c.id, "running")
        result = c.collect(ctx)
        collector_summaries.append({
            "id": result.id,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "warnings": result.warnings,
        })
        all_raw_items.extend(result.items)
        all_migration.extend(result.migration)
        if progress_cb:
            progress_cb(c.id, result.status)

    user_overrides = load_user_overrides()
    with open_db(db_path) as conn:
        db_build = get_meta(conn, "build_date") or "unknown"
        scan_items = []
        for raw in all_raw_items:
            matched  = resolve(raw, conn)
            verdicted = assign_verdict(matched, conn)
            scan_items.append(verdicted)
    apply_user_overrides(scan_items, user_overrides)

    score = compute_score(scan_items)
    distro_recs = recommend_distros(scan_items)

    return ScanResult(
        schema_version=SCHEMA_VERSION,
        scan_id=str(uuid.uuid4()),
        scanned_at=datetime.now(timezone.utc).isoformat(),
        db_build=db_build,
        app_version=__version__,
        system=_system_info(),
        collectors=collector_summaries,
        items=scan_items,
        score=score,
        distro_recs=distro_recs,
        migration=all_migration,
    )


def _system_info() -> dict:
    return {
        "os_version": platform.version(),
        "cpu": platform.processor(),
        "ram_gb": None,
        "secure_boot": None,
    }


def _save_json(result: ScanResult, path: Path) -> None:
    def _serial(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        raise TypeError(type(obj))
    path.write_text(
        json.dumps(dataclasses.asdict(result), indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="linuxready",
        description=f"{APP_NAME} — tells you what it would cost to switch to Linux",
    )
    parser.add_argument("--db",     metavar="PATH", help="Path to compat.db")
    parser.add_argument("--report", metavar="FILE", help="Write HTML report to FILE")
    parser.add_argument("--json",   metavar="FILE", help="Write JSON scan to FILE")
    parser.add_argument("--script", metavar="FILE", help="Write post-install bash script to FILE")
    parser.add_argument("--gui",    action="store_true", help="Launch the GUI")
    args = parser.parse_args()

    if args.gui:
        from .ui.main_window import launch_gui
        launch_gui()
        return

    db_path = Path(args.db) if args.db else DB_PATH
    if not db_path.exists():
        print(f"ERROR: compat.db not found at {db_path}", file=sys.stderr)
        print("Create a development DB with:  python -m linuxready.db.seed", file=sys.stderr)
        sys.exit(1)

    print(f"{APP_NAME} {__version__} — scanning…")
    result = run_scan(db_path, progress_cb=lambda cid, st: print(f"  [{st:8}] {cid}"))

    score = result.score
    print(f"\nReadiness score : {score['value']}/100")
    print(f"Hard blockers   : {score['hard_blockers']}")
    print(f"Unknown items   : {score['unknown_count']}")

    if args.report:
        report_path = Path(args.report)
    elif args.json:
        report_path = None
    else:
        SCANS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = SCANS_DIR / f"scan_{result.scan_id[:8]}.html"

    if report_path:
        report_path.write_text(render_report(result), encoding="utf-8")
        print(f"Report          : {report_path}")

    if args.json:
        json_path = Path(args.json)
        _save_json(result, json_path)
        print(f"JSON            : {json_path}")

    if args.script:
        script_path = Path(args.script)
        script_path.write_text(generate_install_script(result), encoding="utf-8")
        print(f"Install script  : {script_path}")


if __name__ == "__main__":
    main()
