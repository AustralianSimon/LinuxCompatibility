import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from ..config import ACCENT_COLOR, APP_NAME, DEFAULT_THEME
from .views.welcome  import WelcomeView
from .views.scanning import ScanningView
from .views.results  import ResultsView


def launch_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    try:
        import qdarktheme
        qdarktheme.setup_theme(DEFAULT_THEME, custom_colors={"primary": ACCENT_COLOR})
    except ImportError:
        pass  # fall back to native style

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)
        self.setMinimumSize(800, 560)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._welcome  = WelcomeView(self)
        self._scanning = ScanningView(self)
        self._results  = ResultsView(self)

        self._stack.addWidget(self._welcome)
        self._stack.addWidget(self._scanning)
        self._stack.addWidget(self._results)

        self._welcome.scan_requested.connect(self._start_scan)
        self._scanning.scan_complete.connect(self._show_results)
        self._scanning.scan_failed.connect(self._show_welcome)
        self._results.back_requested.connect(self._show_welcome)

    def _start_scan(self) -> None:
        self._stack.setCurrentWidget(self._scanning)
        self._scanning.start()

    def _show_results(self, result) -> None:
        self._results.load(result)
        self._stack.setCurrentWidget(self._results)

    def _show_welcome(self) -> None:
        self._stack.setCurrentWidget(self._welcome)
