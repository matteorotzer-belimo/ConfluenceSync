"""Developer tool: click through the app in demo mode and save screenshots of every view.

    python tools/screenshots.py <output folder>

Uses only the built-in demo (simulated Confluence, sample notes). No network, no real accounts.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "screenshots")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["CONFLUENCESYNC_HOME"] = tempfile.mkdtemp(prefix="cs-shots-")

    from PySide6.QtWidgets import QApplication

    from confluencesync.services import Services
    from confluencesync.ui import worker
    from confluencesync.ui.logo import app_icon
    from confluencesync.ui.main_window import MainWindow
    from confluencesync.ui.style import QSS

    worker.SYNC = True
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    services = Services(Path(os.environ["CONFLUENCESYNC_HOME"]), demo=True)
    win = MainWindow(services, check_updates=False)
    win.resize(1360, 880)
    win.show()

    def shot(name: str) -> None:
        for _ in range(6):
            app.processEvents()
        path = out / f"{name}.png"
        win.grab().save(str(path))
        print("saved", path)

    tutorial = win.pages["tutorial"]
    shot("01-anleitung-willkommen")
    tutorial.show_step(1)
    form = tutorial.confluence_form
    form.url.setText("https://confluence.example.com")
    shot("02-anleitung-confluence")
    form.token.edit.setText("demo-token")
    form.connect_btn.click()
    tutorial.show_step(2)
    tutorial.target.space.setCurrentIndex(tutorial.target.space.findData("DOKU"))
    tutorial.target.set_parent("1001", "Besprechungen")
    shot("03-anleitung-ziel")
    tutorial.show_step(3)
    shot("04-anleitung-notizen")
    tutorial.show_step(4)
    shot("05-anleitung-fertig")
    tutorial._next()

    sources = win.pages["sources"]
    notebook = sources.tree.invisibleRootItem().child(0)
    notebook.setExpanded(True)
    for i in range(notebook.childCount()):
        notebook.child(i).setExpanded(True)
    shot("06-notizen")

    preview = win.pages["preview"]
    win.go("preview", source="demo", source_id="demo-besprechung", origin="sources")
    shot("07-vorschau")
    preview._publish("publish")
    shot("08-veroeffentlicht")
    for page_id in ("demo-idee", "demo-howto"):
        win.go("preview", source="demo", source_id=page_id, origin="sources")
        preview._publish("publish")

    first = services.publications()[0]
    services.demo_edit_confluence(first.id)
    services.demo_edit_source("demo-idee")
    win.go("publications")
    win.pages["publications"].check()
    shot("09-meine-veroeffentlichungen")

    win.go("preview", source=first.source, source_id=first.source_id, origin="publications")
    shot("10-vorschau-konflikt")

    win.go("connections")
    shot("11-verbindungen")
    win.go("settings")
    shot("12-einstellungen")
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
