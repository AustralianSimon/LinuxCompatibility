import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from ..config import ACCENT_COLOR, APP_NAME
from ..settings import load_settings
from .views.welcome  import WelcomeView
from .views.scanning import ScanningView
from .views.results  import ResultsView
from .views.settings import SettingsView


def _apply_theme(theme: str) -> None:
    try:
        import qdarktheme
        qdarktheme.setup_theme(theme, custom_colors={"primary": ACCENT_COLOR})
    except ImportError:
        pass


def launch_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    settings = load_settings()
    _apply_theme(settings.theme)

    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        from ..settings import Settings
        self._settings = settings or Settings()

        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)
        self.setMinimumSize(800, 560)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._welcome  = WelcomeView(self)
        self._scanning = ScanningView(self)
        self._results  = ResultsView(self)
        self._settings_view = SettingsView(self._settings, self)

        for w in (self._welcome, self._scanning, self._results, self._settings_view):
            self._stack.addWidget(w)

        self._welcome.scan_requested.connect(self._start_scan)
        self._welcome.settings_requested.connect(self._show_settings)
        self._scanning.scan_complete.connect(self._show_results)
        self._scanning.scan_failed.connect(self._show_welcome)
        self._results.back_requested.connect(self._show_welcome)
        self._results.settings_requested.connect(self._show_settings)
        self._settings_view.back_requested.connect(self._settings_back)
        self._settings_view.theme_changed.connect(_apply_theme)

        self._pre_settings: QStackedWidget | None = None

    def _start_scan(self) -> None:
        self._stack.setCurrentWidget(self._scanning)
        self._scanning.start()

    def _show_results(self, result) -> None:
        self._results.load(result)
        self._stack.setCurrentWidget(self._results)

    def _show_welcome(self) -> None:
        self._stack.setCurrentWidget(self._welcome)

    def _show_settings(self) -> None:
        self._pre_settings = self._stack.currentWidget()
        self._stack.setCurrentWidget(self._settings_view)

    def _settings_back(self) -> None:
        if self._pre_settings is not None:
            self._stack.setCurrentWidget(self._pre_settings)
        else:
            self._stack.setCurrentWidget(self._welcome)
