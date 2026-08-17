import tempfile
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPushButton,
                                QTabWidget, QVBoxLayout, QWidget, QScrollArea,
                                QFrame, QSizePolicy)

from ...models import ScanResult, ScanItem
from ...report.render import render_report

_VERDICT_LABEL = {
    "native":         "Native Linux",
    "packaged":       "Packaged",
    "layer_excellent":"Works via Proton/Wine",
    "layer_workable": "Works with tweaks",
    "layer_poor":     "Works poorly",
    "blocked":        "Blocked",
    "replace":        "Needs replacement",
    "web":            "Web version",
    "unknown":        "Unknown",
}
_VERDICT_COLOR = {
    "native":         "#06d6a0",
    "packaged":       "#06d6a0",
    "web":            "#06d6a0",
    "layer_excellent":"#06d6a0",
    "layer_workable": "#ffd166",
    "layer_poor":     "#ffd166",
    "replace":        "#ef476f",
    "blocked":        "#ef476f",
    "unknown":        "#888",
}


class ResultsView(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: ScanResult | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(0)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        self._back_btn = QPushButton("← New scan")
        self._back_btn.clicked.connect(self.back_requested)
        self._export_btn = QPushButton("Export report…")
        self._export_btn.clicked.connect(self._export)
        self._open_btn = QPushButton("Open in browser")
        self._open_btn.clicked.connect(self._open_browser)
        for btn in (self._back_btn, self._export_btn, self._open_btn):
            btn.setFixedHeight(32)
        toolbar.addWidget(self._back_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._export_btn)
        toolbar.addWidget(self._open_btn)
        outer.addLayout(toolbar)
        outer.addSpacing(12)

        # ── Score banner ──
        self._score_banner = _ScoreBanner()
        outer.addWidget(self._score_banner)
        outer.addSpacing(12)

        # ── Tabs ──
        self._tabs = QTabWidget()
        self._tab_blockers = _ItemListTab()
        self._tab_games    = _ItemListTab()
        self._tab_apps     = _ItemListTab()
        self._tab_hardware = _ItemListTab()
        self._tabs.addTab(self._tab_blockers, "Blockers")
        self._tabs.addTab(self._tab_games,    "Games")
        self._tabs.addTab(self._tab_apps,     "Apps")
        self._tabs.addTab(self._tab_hardware, "Hardware")
        outer.addWidget(self._tabs)

    def load(self, result: ScanResult) -> None:
        self._result = result
        score = result.score
        self._score_banner.update(score["value"], score["hard_blockers"], score["unknown_count"])

        blockers  = [i for i in result.items if i.is_blocker]
        games     = [i for i in result.items if i.source == "steam"]
        apps      = [i for i in result.items if i.source == "registry_apps"]
        hardware  = [i for i in result.items if i.source in ("hardware", "firmware")]

        self._tab_blockers.load(blockers)
        self._tab_games.load(games)
        self._tab_apps.load(apps)
        self._tab_hardware.load(hardware)

        self._tabs.setTabText(0, f"Blockers ({len(blockers)})")
        self._tabs.setTabText(1, f"Games ({len(games)})")
        self._tabs.setTabText(2, f"Apps ({len(apps)})")
        self._tabs.setTabText(3, f"Hardware ({len(hardware)})")

        if blockers:
            self._tabs.setCurrentIndex(0)
        elif games:
            self._tabs.setCurrentIndex(1)

    def _html(self) -> str:
        assert self._result
        return render_report(self._result)

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report", "linuxready_report.html", "HTML (*.html)"
        )
        if path:
            Path(path).write_text(self._html(), encoding="utf-8")

    def _open_browser(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html",
                                         delete=False, encoding="utf-8") as f:
            f.write(self._html())
            webbrowser.open(f"file://{f.name}")


class _ScoreBanner(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: #16213e; border-radius: 8px; padding: 4px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)

        self._score = QLabel("—")
        self._score.setStyleSheet("font-size: 48px; font-weight: 800; color: #00b4d8;")
        self._label = QLabel("/100  Readiness score")
        self._label.setStyleSheet("font-size: 13px; color: #a0a0b0; margin-top: 14px;")

        self._blockers = QLabel()
        self._unknowns = QLabel()
        for lbl in (self._blockers, self._unknowns):
            lbl.setStyleSheet("font-size: 13px; color: #a0a0b0;")

        lay.addWidget(self._score)
        lay.addWidget(self._label)
        lay.addStretch()
        col = QVBoxLayout()
        col.addWidget(self._blockers)
        col.addWidget(self._unknowns)
        lay.addLayout(col)

    def update(self, score: int, blockers: int, unknowns: int) -> None:
        self._score.setText(str(score))
        bc = "#ef476f" if blockers else "#06d6a0"
        self._blockers.setText(f"<span style='color:{bc};font-weight:700'>{blockers}</span> hard blocker{'s' if blockers != 1 else ''}")
        self._unknowns.setText(f"{unknowns} unknown item{'s' if unknowns != 1 else ''}")


class _ItemListTab(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._container = QWidget()
        self._lay = QVBoxLayout(self._container)
        self._lay.setAlignment(Qt.AlignTop)
        self._lay.setSpacing(4)
        self.setWidget(self._container)

    def load(self, items: list[ScanItem]) -> None:
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sorted_items = sorted(items, key=lambda i: (not i.is_blocker, i.verdict or ""))
        for item in sorted_items:
            self._lay.addWidget(_ItemRow(item))
        if not items:
            placeholder = QLabel("No items")
            placeholder.setStyleSheet("color: #666; font-size: 13px; padding: 20px;")
            placeholder.setAlignment(Qt.AlignCenter)
            self._lay.addWidget(placeholder)


class _ItemRow(QFrame):
    def __init__(self, item: ScanItem):
        super().__init__()
        border_color = "#ef476f" if item.is_blocker else "#2a2a4a"
        self.setStyleSheet(
            f"QFrame {{ background: #16213e; border: 1px solid {border_color}; "
            "border-radius: 6px; padding: 2px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(item.raw_name)
        name.setStyleSheet("font-weight: 600; font-size: 13px;")
        verdict_text = _VERDICT_LABEL.get(item.verdict or "unknown", "Unknown")
        color = _VERDICT_COLOR.get(item.verdict or "unknown", "#888")
        badge = QLabel(verdict_text)
        badge.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; "
            f"border: 1px solid {color}; border-radius: 3px; padding: 1px 6px;"
        )
        top.addWidget(name)
        top.addStretch()
        top.addWidget(badge)
        lay.addLayout(top)

        if item.evidence:
            ev = QLabel(" · ".join(item.evidence[:3]))
            ev.setStyleSheet("font-size: 11px; color: #a0a0b0;")
            ev.setWordWrap(True)
            lay.addWidget(ev)
