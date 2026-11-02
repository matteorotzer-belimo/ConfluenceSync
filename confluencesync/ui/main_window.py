"""Main window: sidebar navigation on the left, the current view on the right."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, GITHUB_REPO, __version__
from ..services import Services
from .connections import ConnectionsPage
from .logo import logo_pixmap
from .preview_page import PreviewPage
from .publications import PublicationsPage
from .settings_page import SettingsPage
from .sources import SourcesPage
from .tutorial import TutorialPage
from .widgets import label
from .worker import run_task

NAV = [  # (page name, text); None = spacer
    ("sources", "📝   Notizen"),
    ("publications", "📚   Meine Veröffentlichungen"),
    ("connections", "🔌   Verbindungen"),
    ("settings", "⚙️   Einstellungen"),
    None,
    ("tutorial", "🎓   Anleitung"),
]


class Banner(QFrame):
    def __init__(self, background: str, colour: str):
        super().__init__()
        self.setObjectName("banner")
        self.setStyleSheet(f"QFrame#banner {{ background: {background}; }} QLabel {{ color: {colour}; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(36, 9, 36, 9)
        self.text = QLabel()
        self.text.setTextFormat(Qt.RichText)
        self.text.setOpenExternalLinks(True)
        self.text.setWordWrap(True)
        row.addWidget(self.text, 1)


class MainWindow(QMainWindow):
    repo_url = f"https://github.com/{GITHUB_REPO}"

    def __init__(self, services: Services, check_updates: bool = True):
        super().__init__()
        self.services = services
        self.setWindowTitle(APP_NAME + (" – Demo" if services.demo else ""))
        self.resize(1320, 860)
        self.setMinimumSize(1080, 680)

        root = QWidget()
        root.setObjectName("content")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.demo_banner = Banner("#f1ebff", "#5b21b6")
        self.demo_banner.text.setText("<b>Demo-Modus</b> – Confluence wird nur simuliert und nichts wird wirklich "
                                      "veröffentlicht. Ideal zum Ausprobieren.")
        self.demo_banner.setVisible(services.demo)
        right.addWidget(self.demo_banner)
        self.update_banner = Banner("#fff1e8", "#9a3412")
        self.update_banner.hide()
        right.addWidget(self.update_banner)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        layout.addLayout(right, 1)
        self.setCentralWidget(root)

        self.pages = {
            "tutorial": TutorialPage(self),
            "sources": SourcesPage(self),
            "preview": PreviewPage(self),
            "publications": PublicationsPage(self),
            "connections": ConnectionsPage(self),
            "settings": SettingsPage(self),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.current = ""
        self.refresh_status()
        self.go("sources" if services.config.tutorial_completed else "tutorial")
        if check_updates and services.config.check_updates and not services.demo:
            run_task(services.check_update, on_done=self._update_found, on_error=lambda _m: None)

    # ------------------------------------------------------------------ layout

    def _sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(262)
        col = QVBoxLayout(bar)
        col.setContentsMargins(16, 20, 16, 16)
        col.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(40))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "brandName", wrap=False))
        names.addWidget(label("Notizen → Confluence", "brandSub", wrap=False))
        brand.addLayout(names, 1)
        col.addLayout(brand)
        col.addSpacing(22)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for entry in NAV:
            if entry is None:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet("background: #2a3245;")
                col.addSpacing(8)
                col.addWidget(line)
                col.addSpacing(8)
                continue
            name, text = entry
            btn = QPushButton(text)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, n=name: self.go(n))
            self.nav.addButton(btn)
            self.nav_buttons[name] = btn
            col.addWidget(btn)
        col.addStretch(1)
        self.status_label = label("", "sideFoot", rich=True)
        col.addWidget(self.status_label)
        col.addSpacing(6)
        col.addWidget(label(f"Version {__version__}", "sideFoot"))
        return bar

    # ------------------------------------------------------------------ navigation

    def go(self, name: str, **kwargs) -> None:
        page = self.pages[name]
        self.current = name
        self.stack.setCurrentWidget(page)
        nav_name = "sources" if name == "preview" else name
        if nav_name in self.nav_buttons:
            self.nav_buttons[nav_name].setChecked(True)
        page.on_show(**kwargs)
        if page.scroll_area is not None:
            page.scroll_area.verticalScrollBar().setValue(0)

    def refresh_status(self) -> None:
        st = self.services.status(check_onenote=False)
        onenote = self.services.auth() is not None and self._onenote_signed_in()

        def dot(ok: bool) -> str:
            return f"<span style='color:{'#4ade80' if ok else '#6b7280'}'>●</span>"

        self.status_label.setText(
            f"{dot(st.confluence_connected)} Confluence<br>{dot(onenote)} OneNote<br>"
            f"{dot(st.notion_connected)} Notion")

    def _onenote_signed_in(self) -> bool:
        try:
            auth = self.services.auth()
            return bool(auth and auth.account())
        except Exception:  # noqa: BLE001 - status display only
            return False

    def _update_found(self, release: dict | None) -> None:
        if not release:
            return
        self.update_banner.text.setText(
            f"<b>Neue Version {escape(release['version'])} verfügbar.</b> "
            f"<a href='{escape(release['url'] or self.repo_url)}'>Jetzt herunterladen</a> – "
            "einfach die neue ConfluenceSync.exe statt der alten verwenden. Deine Verbindungen bleiben erhalten.")
        self.update_banner.show()
