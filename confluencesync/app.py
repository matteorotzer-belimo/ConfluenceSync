"""Start the desktop app: `python -m confluencesync [--demo]` or ConfluenceSync.exe."""
from __future__ import annotations

import argparse
import logging
import os
import sys

from . import APP_NAME, __version__
from .paths import data_dir

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Notizen aus OneNote und Notion nach Confluence.")
    parser.add_argument("--demo", action="store_true", help="Demo mode with sample notes and simulated Confluence")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--smoke-test", action="store_true", help="Open the window and quit after 2 s (for CI)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # In the windowed exe there is no console: give argparse/print somewhere harmless to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    args = parse_args(argv)
    from . import logs

    home = data_dir()
    logs.setup(home / "logs")
    log.info("starting %s %s (demo=%s)", APP_NAME, __version__, args.demo)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .services import Services
    from .ui.logo import app_icon
    from .ui.main_window import MainWindow
    from .ui.style import QSS

    if sys.platform == "win32":
        try:  # own taskbar icon instead of the Python one
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Belimo.ConfluenceSync")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())

    services = Services(home, demo=args.demo)
    window = MainWindow(services, check_updates=not args.smoke_test)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(2000, app.quit)
    code = app.exec()
    if args.smoke_test:
        log.info("smoke test ok (exit code %s)", code)
        print(f"{APP_NAME} {__version__} smoke test ok")
    return code


if __name__ == "__main__":
    sys.exit(main())
