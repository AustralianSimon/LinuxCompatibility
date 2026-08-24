from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QLabel, QPushButton, QVBoxLayout, QWidget,
                                QFrame, QHBoxLayout)

from ...config import APP_NAME
from .db_update import DbUpdateDialog


class WelcomeView(QWidget):
    scan_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("welcome-card")
        card.setFixedWidth(540)
        lay = QVBoxLayout(card)
        lay.setSpacing(18)
        lay.setContentsMargins(40, 40, 40, 40)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #00b4d8;")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Linux compatibility scanner")
        subtitle.setStyleSheet("font-size: 14px; color: #a0a0b0;")
        subtitle.setAlignment(Qt.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #2a2a4a;")

        what = QLabel(
            "<b>What this does</b><br>"
            "Inventories your installed apps, games, and hardware — "
            "then tells you exactly what would work on Linux, what needs a "
            "workaround, and what would block you."
        )
        what.setWordWrap(True)
        what.setStyleSheet("font-size: 13px; color: #c0c0d0; line-height: 1.5;")

        privacy = QLabel(
            "\U0001f512  Your scan never leaves your PC. Read-only."
        )
        privacy.setStyleSheet("font-size: 12px; color: #06d6a0; padding: 8px 0;")
        privacy.setAlignment(Qt.AlignCenter)

        self._btn = QPushButton("Start Scan")
        self._btn.setFixedHeight(44)
        self._btn.setStyleSheet(
            "QPushButton { background: #00b4d8; color: #fff; font-size: 14px; "
            "font-weight: 600; border-radius: 6px; }"
            "QPushButton:hover { background: #0096c7; }"
            "QPushButton:pressed { background: #0077b6; }"
        )
        self._btn.clicked.connect(self.scan_requested)

        self._update_btn = QPushButton("Update database…")
        self._update_btn.setFixedHeight(32)
        self._update_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #a0a0b0; "
            "font-size: 12px; border: 1px solid #2a2a4a; border-radius: 5px; }"
            "QPushButton:hover { color: #00b4d8; border-color: #00b4d8; }"
        )
        self._update_btn.clicked.connect(self._open_update_dialog)

        lay.addWidget(title)
        lay.addWidget(subtitle)
        lay.addWidget(divider)
        lay.addWidget(what)
        lay.addWidget(privacy)
        lay.addWidget(self._btn)
        lay.addWidget(self._update_btn)

        outer.addWidget(card)

    def _open_update_dialog(self) -> None:
        dlg = DbUpdateDialog(self)
        dlg.exec()
