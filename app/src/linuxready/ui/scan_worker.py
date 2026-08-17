from PySide6.QtCore import QThread, Signal

from ..__main__ import run_scan
from ..config import DB_PATH
from ..models import ScanResult


class ScanWorker(QThread):
    progress = Signal(str, str)   # collector_id, status
    complete = Signal(object)     # ScanResult
    failed   = Signal(str)        # error message

    def run(self) -> None:
        try:
            result: ScanResult = run_scan(
                db_path=DB_PATH,
                progress_cb=lambda cid, st: self.progress.emit(cid, st),
            )
            self.complete.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
