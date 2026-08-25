import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QHBoxLayout,
                                QLabel, QPushButton, QRadioButton, QScrollArea,
                                QVBoxLayout, QWidget)

from ...config import ACCENT_COLOR, DB_PATH, SCANS_DIR
from ...scan_persist import list_scans
from ...settings import Settings, save_settings

_SECTION_STYLE = (
    "font-size: 10px; font-weight: 700; letter-spacing: 0.08em; "
    f"color: {ACCENT_COLOR}; padding: 16px 0 6px;"
)
_ROW_STYLE = "font-size: 13px; color: #c0c0d0;"
_HINT_STYLE = "font-size: 11px; color: #666; padding-left: 22px;"


class SettingsView(QWidget):
    back_requested = Signal()
    theme_changed  = Signal(str)   # "dark" | "light" | "auto"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(0)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        back = QPushButton("← Back")
        back.setFixedHeight(32)
        back.clicked.connect(self.back_requested)
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #c0c0d0;")
        toolbar.addWidget(back)
        toolbar.addSpacing(16)
        toolbar.addWidget(title)
        toolbar.addStretch()
        outer.addLayout(toolbar)
        outer.addSpacing(12)

        # ── Scrollable body ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setAlignment(Qt.AlignTop)
        lay.setSpacing(4)
        lay.setContentsMargins(0, 0, 16, 16)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ── Appearance ──
        lay.addWidget(_section("APPEARANCE"))

        lay.addWidget(_row("Theme"))
        self._theme_group = QButtonGroup(self)
        for value, label in (("dark", "Dark"), ("light", "Light"), ("auto", "Auto (follow system)")):
            rb = QRadioButton(label)
            rb.setStyleSheet(_ROW_STYLE)
            rb.setChecked(settings.theme == value)
            rb.toggled.connect(lambda checked, v=value: self._on_theme(checked, v))
            self._theme_group.addButton(rb)
            lay.addWidget(rb)

        # ── Scan ──
        lay.addWidget(_section("SCAN"))

        self._portable_cb = QCheckBox("Include portable apps")
        self._portable_cb.setStyleSheet(_ROW_STYLE)
        self._portable_cb.setChecked(settings.portable_scan)
        self._portable_cb.toggled.connect(self._on_portable)
        lay.addWidget(self._portable_cb)

        hint = QLabel(
            "Scans %LOCALAPPDATA%\\Programs and Start Menu shortcuts. "
            "Adds a few seconds; may surface false positives."
        )
        hint.setStyleSheet(_HINT_STYLE)
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # ── Database ──
        lay.addWidget(_section("DATABASE"))
        self._db_label = QLabel()
        self._db_label.setStyleSheet(_ROW_STYLE)
        self._db_label.setWordWrap(True)
        lay.addWidget(self._db_label)
        self._refresh_db_info()

        from .db_update import DbUpdateDialog
        update_btn = QPushButton("Check for database update…")
        update_btn.setFixedHeight(32)
        update_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #a0a0b0; "
            "font-size: 12px; border: 1px solid #2a2a4a; border-radius: 5px; "
            "padding: 0 12px; margin-top: 8px; }"
            "QPushButton:hover { color: #00b4d8; border-color: #00b4d8; }"
        )
        update_btn.clicked.connect(lambda: DbUpdateDialog(self).exec())
        btn_row = QHBoxLayout()
        btn_row.addWidget(update_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # ── Recent scans ──
        lay.addWidget(_section("RECENT SCANS"))
        scans = list_scans()
        if scans:
            for scan_path in scans[:10]:
                row = QHBoxLayout()
                stat = scan_path.stat()
                size_kb = stat.st_size // 1024
                name_lbl = QLabel(
                    f"<span style='font-size:12px;color:#c0c0d0;'>{scan_path.name}</span>"
                    f"  <span style='font-size:10px;color:#555;'>{size_kb} KB</span>"
                )
                row.addWidget(name_lbl, 1)
                lay.addLayout(row)
        else:
            lay.addWidget(QLabel(
                "No saved scans yet — run a scan to create one."
            ))

        open_dir_btn = QPushButton("Open scans folder ↗")
        open_dir_btn.setFixedHeight(30)
        open_dir_btn.setStyleSheet(
            "QPushButton { color: #a0a0b0; font-size: 11px; border: none; "
            "background: none; text-decoration: underline; padding: 0; margin-top: 4px; }"
            "QPushButton:hover { color: #00b4d8; }"
        )
        open_dir_btn.clicked.connect(self._open_scans_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(open_dir_btn)
        dir_row.addStretch()
        lay.addLayout(dir_row)

        lay.addStretch()

    def _open_scans_dir(self) -> None:
        SCANS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(SCANS_DIR))

    def _on_theme(self, checked: bool, value: str) -> None:
        if not checked:
            return
        self._settings.theme = value
        save_settings(self._settings)
        self.theme_changed.emit(value)

    def _on_portable(self, checked: bool) -> None:
        self._settings.portable_scan = checked
        save_settings(self._settings)

    def _refresh_db_info(self) -> None:
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            build = conn.execute(
                "SELECT value FROM meta WHERE key = 'build_date'"
            ).fetchone()
            conn.close()
            build_str = build[0] if build else "unknown"
            self._db_label.setText(
                f"<b>{DB_PATH.name}</b><br>"
                f"<span style='color:#666;font-size:11px;'>"
                f"Built: {build_str} &nbsp;·&nbsp; {DB_PATH}</span>"
            )
        except Exception:
            self._db_label.setText(
                f"<b>{DB_PATH.name}</b><br>"
                f"<span style='color:#666;font-size:11px;'>{DB_PATH}</span>"
            )


def _section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SECTION_STYLE)
    return lbl


def _row(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_ROW_STYLE)
    return lbl
