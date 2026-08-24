from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout,
)

from ...db.update import download_db, run_harvester


class _Worker(QObject):
    log = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, mode: str) -> None:
        super().__init__()
        self._mode = mode

    def run(self) -> None:
        try:
            if self._mode == "download":
                download_db(progress_cb=self.log.emit)
            else:
                run_harvester(progress_cb=self.log.emit)
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class DbUpdateDialog(QDialog):
    db_updated = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update Database")
        self.setMinimumWidth(540)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        heading = QLabel("Choose how to update the compatibility database:")
        heading.setStyleSheet("font-size: 13px; font-weight: 600;")
        lay.addWidget(heading)

        self._group = QButtonGroup(self)
        self._radio_download = QRadioButton(
            "Download from GitHub  (fast — uses the pre-built database)"
        )
        self._radio_harvester = QRadioButton(
            "Run harvester locally  (slow — builds a fresh database from upstream sources)"
        )
        self._radio_download.setChecked(True)
        self._group.addButton(self._radio_download, 0)
        self._group.addButton(self._radio_harvester, 1)
        lay.addWidget(self._radio_download)
        lay.addWidget(self._radio_harvester)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2a2a4a;")
        lay.addWidget(sep)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(200)
        self._log.setStyleSheet(
            "font-family: monospace; font-size: 11px; "
            "background: #0d1117; color: #c0c0d0;"
        )
        lay.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setFixedHeight(36)
        self._start_btn.setStyleSheet(
            "QPushButton { background: #00b4d8; color: #fff; font-size: 13px; "
            "font-weight: 600; border-radius: 5px; }"
            "QPushButton:hover { background: #0096c7; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._start_btn.clicked.connect(self._start)

        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedHeight(36)
        self._close_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._close_btn)
        lay.addLayout(btn_row)

        self._thread: QThread | None = None
        self._worker: _Worker | None = None

    def _start(self) -> None:
        mode = "download" if self._radio_download.isChecked() else "harvester"
        self._log.clear()
        self._set_busy(True)

        self._worker = _Worker(mode)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._log.appendPlainText)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_done(self) -> None:
        self._set_busy(False)
        self._log.appendPlainText("\nDatabase updated successfully.")
        self.db_updated.emit()

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self._log.appendPlainText(f"\nError: {msg}")

    def _set_busy(self, busy: bool) -> None:
        self._start_btn.setEnabled(not busy)
        self._radio_download.setEnabled(not busy)
        self._radio_harvester.setEnabled(not busy)
        self._close_btn.setEnabled(not busy)
