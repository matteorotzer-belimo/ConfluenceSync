"""«Meine Veröffentlichungen»: every published note with its status, plus the history."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QMenu, QScrollArea,
                               QStackedWidget, QTabBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..model import SOURCE_LABELS
from ..store import Mapping
from ..sync import planner
from .page import Page
from .widgets import Badge, Card, Note, button, clear, confirm, hbox, label, open_url
from .worker import run_task

ACTIONS = {"create": "Erstellt", "update": "Aktualisiert", "keep": "Confluence behalten",
           "forget": "Verknüpfung entfernt"}
NEEDS_ACTION = {planner.SOURCE_CHANGED, planner.CONFLUENCE_CHANGED, planner.REVIEW, planner.PAGE_MISSING}


def local_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


class PublicationsPage(Page):
    title = "Meine Veröffentlichungen"
    subtitle = "Alle Notizen, die du nach Confluence gebracht hast – und ob sie noch aktuell sind."

    def __init__(self, win):
        super().__init__(win, scroll=False)
        self.checked_once = False
        self.check_btn = button("↻ Status prüfen", "primary", self.check)
        self.actions.addWidget(self.check_btn)

        self.summary = label("", "muted")
        self.body.addWidget(self.summary)
        self.message = Note("info", "")
        self.message.hide()
        self.body.addWidget(self.message)

        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.addTab("Seiten")
        self.tabs.addTab("Verlauf")
        self.body.addWidget(self.tabs)
        self.stack = QStackedWidget()
        self.tabs.currentChanged.connect(self._tab)
        self.body.addWidget(self.stack, 1)

        self.empty = Card()
        self.empty.add(label("Noch nichts veröffentlicht", "h2"))
        self.empty.add(label("Wähle unter «Notizen» eine Seite aus, prüfe die Vorschau und veröffentliche sie. "
                             "Danach erscheint sie hier.", "muted"))
        self.empty.add(hbox(button("Zu den Notizen", "primary", lambda: self.win.go("sources")), None))
        self.empty.body.addStretch(1)

        self.list_area = QScrollArea()
        self.list_area.setWidgetResizable(True)
        self.list_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_body = QWidget()
        list_body.setObjectName("scrollBody")
        self.rows = QVBoxLayout(list_body)
        self.rows.setContentsMargins(0, 0, 4, 0)
        self.rows.setSpacing(10)
        self.list_area.setWidget(list_body)
        self.table = self.list_area
        self.pages = QStackedWidget()
        self.pages.addWidget(self.empty)
        self.pages.addWidget(self.table)
        self.stack.addWidget(self.pages)

        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Zeit", "Seite", "Aktion", "Ergebnis"])
        self._setup(self.history)
        self.history.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.stack.addWidget(self.history)

    @staticmethod
    def _setup(table: QTableWidget) -> None:
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().setDefaultSectionSize(52)

    # ------------------------------------------------------------------ show

    def on_show(self, **kwargs) -> None:
        self.render()
        if not self.checked_once and self.services.publications() and self.services.status().confluence_connected:
            self.check()

    def _tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 1:
            self._render_history()

    def check(self) -> None:
        self.checked_once = True
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Wird geprüft …")

        def done(_):
            self.check_btn.setEnabled(True)
            self.check_btn.setText("↻ Status prüfen")
            self.message.hide()
            self.render()

        def failed(message: str):
            self.check_btn.setEnabled(True)
            self.check_btn.setText("↻ Status prüfen")
            self.message.set_plain("err", message)
            self.message.show()

        run_task(self.services.check_all, on_done=done, on_error=failed)

    # ------------------------------------------------------------------ render

    def render(self) -> None:
        mappings = self.services.publications()
        self.pages.setCurrentIndex(1 if mappings else 0)
        todo = sum(1 for m in mappings if m.status in NEEDS_ACTION)
        if mappings:
            text = f"{len(mappings)} veröffentlichte Seite(n)"
            text += f" · {todo} brauchen deine Aufmerksamkeit" if todo else " · alles aktuell 👍"
            checked = max((m.last_checked_at or "" for m in mappings), default="")
            if checked:
                text += f" · zuletzt geprüft {local_time(checked)}"
            self.summary.setText(text)
        else:
            self.summary.setText("")
        clear(self.rows)
        for m in mappings:
            self.rows.addWidget(self._row(m))
        self.rows.addStretch(1)
        if self.tabs.currentIndex() == 1:
            self._render_history()

    def _row(self, m: Mapping) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 14, 14)
        row.setSpacing(14)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        title = label(m.title or m.source_title or "", "h3")
        if m.source_title and m.source_title != m.title:
            title.setToolTip(f"Notiz: {m.source_title}")
        texts.addWidget(title)
        meta = f"{SOURCE_LABELS.get(m.source, m.source)}  ·  Space {m.space or '?'}"
        if m.last_run_at:
            meta += f"  ·  veröffentlicht {local_time(m.last_run_at)}"
        texts.addWidget(label(meta, "muted"))
        if m.last_error:
            texts.addWidget(label("⚠ " + m.last_error, "muted"))
        row.addLayout(texts, 1)
        row.addWidget(Badge(m.status, planner.STATUS_LABELS.get(m.status, m.status)), 0, Qt.AlignVCenter)

        if m.status in NEEDS_ACTION:
            text = {planner.SOURCE_CHANGED: "Aktualisieren …", planner.PAGE_MISSING: "Neu veröffentlichen …"}.get(
                m.status, "Prüfen und entscheiden …")
            main = button(text, "primary", lambda _=False, x=m: self._open_preview(x))
        else:
            main = button("Vorschau", None, lambda _=False, x=m: self._open_preview(x))
        main.setMinimumWidth(190)
        open_btn = button("In Confluence ↗", "ghost", lambda _=False, x=m: open_url(x.confluence_url or ""))
        open_btn.setEnabled(bool(m.confluence_url) and m.status != planner.PAGE_MISSING)
        more = button("•••", "ghost")
        more.setToolTip("Weitere Aktionen")
        more.clicked.connect(lambda _=False, x=m, b=more: self._menu(x, b))
        for widget in (main, open_btn, more):
            row.addWidget(widget, 0, Qt.AlignVCenter)
        return card

    def _render_history(self) -> None:
        runs = self.services.history()
        self.history.setRowCount(len(runs))
        for row, run in enumerate(runs):
            self.history.setItem(row, 0, QTableWidgetItem(local_time(run.at)))
            self.history.setItem(row, 1, QTableWidgetItem(run.title or ""))
            self.history.setItem(row, 2, QTableWidgetItem(ACTIONS.get(run.action, run.action)))
            ok = run.result == "ok"
            result = QTableWidgetItem(("✓ " if ok else "✗ ") + (run.message or ""))
            result.setForeground(Qt.darkGreen if ok else Qt.red)
            self.history.setItem(row, 3, result)

    # ------------------------------------------------------------------ actions

    def _open_preview(self, m: Mapping) -> None:
        self.win.go("preview", source=m.source, source_id=m.source_id, origin="publications")

    def _menu(self, m: Mapping, anchor) -> None:
        menu = QMenu(self)
        if m.source_url:
            menu.addAction(f"In {SOURCE_LABELS.get(m.source, m.source)} öffnen", lambda: open_url(m.source_url))
        menu.addAction("Verknüpfung entfernen …", lambda: self._forget(m))
        if self.services.demo:
            menu.addSeparator()
            menu.addAction("Demo: Seite in Confluence von Hand ändern", lambda: self._demo(
                self.services.demo_edit_confluence, m.id))
            if m.source == "demo":
                menu.addAction("Demo: Notiz in der Quelle ändern", lambda: self._demo(
                    self.services.demo_edit_source, m.source_id))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _demo(self, fn, arg) -> None:
        fn(arg)
        self.check()

    def _forget(self, m: Mapping) -> None:
        if confirm(self, "Verknüpfung entfernen?",
                   f"ConfluenceSync vergisst die Verbindung zwischen der Notiz und «{m.title}».\n\n"
                   "Die Confluence-Seite selbst bleibt bestehen und wird nicht gelöscht.",
                   "Verknüpfung entfernen", danger=True):
            self.services.forget(m.id)
            self.render()
