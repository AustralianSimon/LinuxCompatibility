import tempfile
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                QFileDialog, QFormLayout, QHBoxLayout,
                                QLabel, QLineEdit, QMessageBox, QPushButton,
                                QTabWidget, QVBoxLayout, QWidget, QScrollArea,
                                QFrame, QSizePolicy)

from ...matcher.resolver import bad_match_url
from ...models import MigrationItem, ScanResult, ScanItem
from ...overrides import save_user_override
from ...report.install_script import generate_install_script
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
        self._script_btn = QPushButton("Save install script…")
        self._script_btn.clicked.connect(self._export_script)
        self._open_btn = QPushButton("Open in browser")
        self._open_btn.clicked.connect(self._open_browser)
        for btn in (self._back_btn, self._export_btn, self._script_btn, self._open_btn):
            btn.setFixedHeight(32)
        toolbar.addWidget(self._back_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._script_btn)
        toolbar.addWidget(self._export_btn)
        toolbar.addWidget(self._open_btn)
        outer.addLayout(toolbar)
        outer.addSpacing(12)

        # ── Score banner ──
        self._score_banner = _ScoreBanner()
        outer.addWidget(self._score_banner)
        outer.addSpacing(12)

        # ── Distro recommendations ──
        self._distro_panel = _DistroPanel()
        outer.addWidget(self._distro_panel)
        outer.addSpacing(8)

        # ── Tabs ──
        self._tabs = QTabWidget()
        self._tab_blockers  = _ItemListTab()
        self._tab_games     = _ItemListTab()
        self._tab_apps      = _ItemListTab()
        self._tab_hardware  = _ItemListTab()
        self._tab_migration = _MigrationTab()
        self._tabs.addTab(self._tab_blockers,  "Blockers")
        self._tabs.addTab(self._tab_games,     "Games")
        self._tabs.addTab(self._tab_apps,      "Apps")
        self._tabs.addTab(self._tab_hardware,  "Hardware")
        self._tabs.addTab(self._tab_migration, "Migration")
        outer.addWidget(self._tabs)

    def load(self, result: ScanResult) -> None:
        self._result = result
        score = result.score
        self._score_banner.update(score["value"], score["hard_blockers"], score["unknown_count"])
        self._distro_panel.load(result.distro_recs)

        blockers  = [i for i in result.items if i.is_blocker]
        games     = [i for i in result.items if i.source in ("steam", "epic", "gog")]
        apps      = [i for i in result.items if i.source in ("registry_apps", "msix")]
        hardware  = [i for i in result.items if i.source in ("hardware", "firmware")]

        db_build = result.db_build
        self._tab_blockers.load(blockers, db_build)
        self._tab_games.load(games, db_build)
        self._tab_apps.load(apps, db_build)
        self._tab_hardware.load(hardware, db_build)
        self._tab_migration.load(result.migration)

        found_migration = [m for m in result.migration if m.found]
        total_gb = sum(m.size_gb for m in found_migration)
        self._tabs.setTabText(0, f"Blockers ({len(blockers)})")
        self._tabs.setTabText(1, f"Games ({len(games)})")
        self._tabs.setTabText(2, f"Apps ({len(apps)})")
        self._tabs.setTabText(3, f"Hardware ({len(hardware)})")
        self._tabs.setTabText(4, f"Migration ({total_gb:.1f} GB)")

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

    def _export_script(self) -> None:
        assert self._result
        path, _ = QFileDialog.getSaveFileName(
            self, "Save install script", "linuxready_install.sh",
            "Shell script (*.sh);;All files (*)"
        )
        if path:
            Path(path).write_text(
                generate_install_script(self._result), encoding="utf-8"
            )

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

    def load(self, items: list[ScanItem], db_build: str = "") -> None:
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sorted_items = sorted(items, key=lambda i: (not i.is_blocker, i.verdict or ""))
        for item in sorted_items:
            self._lay.addWidget(_ItemRow(item, db_build))
        if not items:
            placeholder = QLabel("No items")
            placeholder.setStyleSheet("color: #666; font-size: 13px; padding: 20px;")
            placeholder.setAlignment(Qt.AlignCenter)
            self._lay.addWidget(placeholder)


class _ItemRow(QFrame):
    def __init__(self, item: ScanItem, db_build: str = ""):
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

        if item.source != "firmware":
            bottom = QHBoxLayout()
            bottom.addStretch()
            if item.matched_id:
                override_btn = QPushButton("Override verdict…")
                override_btn.setStyleSheet(
                    "QPushButton { color: #555; font-size: 10px; border: none; "
                    "background: none; padding: 0; margin-right: 12px; "
                    "text-decoration: underline; cursor: pointer; }"
                    "QPushButton:hover { color: #ffd166; }"
                )
                override_btn.setCursor(Qt.PointingHandCursor)
                override_btn.clicked.connect(
                    lambda checked=False, i=item: _OverrideDialog.run(i, override_btn.window())
                )
                bottom.addWidget(override_btn)
            report_link = QPushButton("Report wrong match")
            report_link.setStyleSheet(
                "QPushButton { color: #555; font-size: 10px; border: none; "
                "background: none; padding: 0; text-decoration: underline; cursor: pointer; }"
                "QPushButton:hover { color: #00b4d8; }"
            )
            report_link.setCursor(Qt.PointingHandCursor)
            url = bad_match_url(item, db_build)
            report_link.clicked.connect(lambda: webbrowser.open(url))
            bottom.addWidget(report_link)
            lay.addLayout(bottom)


_CATEGORY_LABEL = {"documents": "User folders", "browser": "Browsers", "mail": "Mail"}
_MIGRATE_COLOR  = {"documents": "#06d6a0", "browser": "#00b4d8", "mail": "#ffd166"}


class _MigrationTab(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._container = QWidget()
        self._lay = QVBoxLayout(self._container)
        self._lay.setAlignment(Qt.AlignTop)
        self._lay.setSpacing(8)
        self.setWidget(self._container)

    def load(self, items: list[MigrationItem]) -> None:
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        found = [i for i in items if i.found]
        if not found:
            lbl = QLabel("No user data found (scan may not have run on Windows).")
            lbl.setStyleSheet("color: #666; font-size: 13px; padding: 20px;")
            lbl.setAlignment(Qt.AlignCenter)
            self._lay.addWidget(lbl)
            return

        total_gb = sum(i.size_gb for i in found)
        summary = QLabel(
            f"<b>Total data to migrate: {total_gb:.1f} GB</b> across "
            f"{len(found)} location{'s' if len(found) != 1 else ''} found"
        )
        summary.setStyleSheet("font-size: 13px; color: #c0c0d0; padding: 8px 4px;")
        self._lay.addWidget(summary)

        for category in ("documents", "browser", "mail"):
            cat_items = [i for i in found if i.category == category]
            if not cat_items:
                continue
            header = QLabel(_CATEGORY_LABEL.get(category, category).upper())
            header.setStyleSheet(
                f"font-size: 10px; font-weight: 700; color: {_MIGRATE_COLOR.get(category, '#888')};"
                " letter-spacing: 0.08em; padding: 12px 4px 4px;"
            )
            self._lay.addWidget(header)
            for item in cat_items:
                self._lay.addWidget(_MigrationRow(item))


class _MigrationRow(QFrame):
    def __init__(self, item: MigrationItem):
        super().__init__()
        self.setStyleSheet(
            "QFrame { background: #16213e; border: 1px solid #2a2a4a; "
            "border-radius: 6px; padding: 2px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(item.name)
        name.setStyleSheet("font-weight: 600; font-size: 13px;")
        size_color = "#ffd166" if item.size_gb > 10 else "#06d6a0"
        size_lbl = QLabel(f"{item.size_gb:.1f} GB")
        size_lbl.setStyleSheet(f"color: {size_color}; font-size: 13px; font-weight: 600;")
        top.addWidget(name)
        top.addStretch()
        top.addWidget(size_lbl)
        lay.addLayout(top)

        if item.note:
            note = QLabel(item.note)
            note.setStyleSheet("font-size: 11px; color: #a0a0b0;")
            note.setWordWrap(True)
            lay.addWidget(note)


class _DistroPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QFrame { background: transparent; }")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(10)

    def load(self, recs) -> None:
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not recs:
            self.hide()
            return

        self.show()
        for i, rec in enumerate(recs):
            self._lay.addWidget(_DistroCard(rec, top=(i == 0)))
        self._lay.addStretch()


class _DistroCard(QFrame):
    def __init__(self, rec, top: bool = False):
        super().__init__()
        border = "#00b4d8" if top else "#2a2a4a"
        self.setStyleSheet(
            f"QFrame {{ background: #16213e; border: 1px solid {border}; "
            "border-radius: 8px; padding: 2px; }}"
        )
        self.setFixedWidth(240)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        header = QHBoxLayout()
        name = QLabel(f"{'★ ' if top else ''}{rec.name}")
        name.setStyleSheet("font-weight: 700; font-size: 13px; color: #00b4d8;")
        header.addWidget(name)
        header.addStretch()
        lay.addLayout(header)

        tagline = QLabel(rec.tagline)
        tagline.setStyleSheet("font-size: 10px; color: #a0a0b0;")
        tagline.setWordWrap(True)
        lay.addWidget(tagline)

        if rec.reasons:
            lay.addSpacing(4)
            for reason in rec.reasons[:2]:
                bullet = QLabel(f"· {reason}")
                bullet.setStyleSheet("font-size: 10px; color: #c0c0d0;")
                bullet.setWordWrap(True)
                lay.addWidget(bullet)

        lay.addSpacing(6)
        link_btn = QPushButton("Visit website →")
        link_btn.setStyleSheet(
            "QPushButton { color: #0077b6; font-size: 10px; border: none; "
            "background: none; padding: 0; text-align: left; }"
            "QPushButton:hover { color: #00b4d8; }"
        )
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.clicked.connect(lambda: webbrowser.open(rec.url))
        lay.addWidget(link_btn)


_OVERRIDE_VERDICTS = [
    ("native",          "Native Linux"),
    ("packaged",        "Packaged (Flatpak/Snap/apt)"),
    ("web",             "Web version available"),
    ("layer_excellent", "Works via Proton/Wine (excellent)"),
    ("layer_workable",  "Works via Proton/Wine (workable)"),
    ("layer_poor",      "Works via Proton/Wine (poor)"),
    ("replace",         "Needs replacement"),
    ("blocked",         "Blocked"),
    ("unknown",         "Unknown"),
]


class _OverrideDialog(QDialog):
    """Let the user pin a custom verdict for a matched app or game."""

    def __init__(self, item: ScanItem, parent=None):
        super().__init__(parent)
        self._item = item
        self.setWindowTitle("Override verdict")
        self.setMinimumWidth(420)

        form = QFormLayout()
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 8)

        form.addRow(QLabel(f"<b>{item.raw_name}</b>"))
        id_lbl = QLabel(f"<span style='color:#666;font-size:11px;'>{item.matched_id}</span>")
        form.addRow(id_lbl)
        form.addRow(QLabel(""))

        self._combo = QComboBox()
        for value, label in _OVERRIDE_VERDICTS:
            self._combo.addItem(label, userData=value)
        current = item.verdict or "unknown"
        idx = next((i for i, (v, _) in enumerate(_OVERRIDE_VERDICTS) if v == current), 0)
        self._combo.setCurrentIndex(idx)
        form.addRow("Verdict:", self._combo)

        self._note = QLineEdit()
        self._note.setPlaceholderText("e.g. Works with Bottles 51.x  (optional)")
        form.addRow("Note:", self._note)

        contrib = QLabel(
            "<span style='color:#666;font-size:10px;'>"
            "To share this fix with the community, open a PR against<br>"
            "harvester/data/overrides/apps.yaml after confirming it works."
            "</span>"
        )
        contrib.setWordWrap(True)
        form.addRow(contrib)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    @staticmethod
    def run(item: ScanItem, parent=None) -> None:
        dlg = _OverrideDialog(item, parent)
        if dlg.exec() != QDialog.Accepted:
            return
        verdict = dlg._combo.currentData()
        note    = dlg._note.text().strip()
        try:
            save_user_override(item.matched_id, verdict, note)
            QMessageBox.information(
                parent, "Override saved",
                f"Verdict for '{item.raw_name}' set to '{verdict}'.\n\n"
                "Run a new scan to see the updated result."
            )
        except Exception as exc:
            QMessageBox.critical(parent, "Error", f"Could not save override:\n{exc}")
