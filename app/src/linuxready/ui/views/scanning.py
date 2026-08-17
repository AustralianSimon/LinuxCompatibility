from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QLabel, QPushButton, QVBoxLayout, QWidget,
                                QProgressBar, QFrame)

from ..scan_worker import ScanWorker


class ScanningView(QWidget):
    scan_complete = Signal(object)  # ScanResult
    scan_failed   = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(20)

        self._title = QLabel("Scanning your system…")
        self._title.setStyleSheet("font-size: 20px; font-weight: 600; color: #00b4d8;")
        self._title.setAlignment(Qt.AlignCenter)

        self._status = QLabel("Initialising…")
        self._status.setStyleSheet("font-size: 13px; color: #a0a0b0;")
        self._status.setAlignment(Qt.AlignCenter)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate
        self._bar.setFixedWidth(400)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            "QProgressBar { background: #2a2a4a; border-radius: 3px; }"
            "QProgressBar::chunk { background: #00b4d8; border-radius: 3px; }"
        )

        self._cancel = QPushButton("Cancel")
        self._cancel.setFixedWidth(100)
        self._cancel.setStyleSheet("color: #a0a0b0; border: 1px solid #2a2a4a; border-radius: 4px;")
        self._cancel.clicked.connect(self._on_cancel)

        self._error = QLabel("")
        self._error.setStyleSheet("color: #ef476f; font-size: 13px;")
        self._error.setAlignment(Qt.AlignCenter)
        self._error.hide()

        lay.addWidget(self._title)
        lay.addWidget(self._status)
        lay.addWidget(self._bar, alignment=Qt.AlignHCenter)
        lay.addWidget(self._error)
        lay.addWidget(self._cancel, alignment=Qt.AlignHCenter)

        self._worker: ScanWorker | None = None

    def start(self) -> None:
        self._error.hide()
        self._status.setText("Initialising…")
        self._worker = ScanWorker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.complete.connect(self._on_complete)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, collector_id: str, status: str) -> None:
        labels = {
            "steam":         "Steam games",
            "registry_apps": "Installed apps",
            "hardware":      "Hardware & firmware",
        }
        label = labels.get(collector_id, collector_id)
        if status == "running":
            self._status.setText(f"Scanning {label}…")
        else:
            self._status.setText(f"{label}: {status}")

    def _on_complete(self, result) -> None:
        self._status.setText("Done.")
        self.scan_complete.emit(result)

    def _on_failed(self, msg: str) -> None:
        self._error.setText(f"Scan failed: {msg}")
        self._error.show()
        self.scan_failed.emit()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.scan_failed.emit()
