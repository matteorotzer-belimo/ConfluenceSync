"""Browse notes: notebook -> section -> page (OneNote) or shared pages (Notion)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QHeaderView, QLineEdit, QTabBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..connectors.base import SourceNode
from .page import Page
from .widgets import Note, button, hbox, label
from .worker import run_task

ICONS = {"notebook": "📓", "section_group": "🗂️", "section": "📑", "page": "📄", "workspace": "🗂️"}
LOADING = "__loading__"
HINTS = {
    "onenote": "Klappe ein Notizbuch und einen Abschnitt auf. Doppelklick auf eine Seite öffnet die Vorschau.",
    "notion": "Hier erscheinen alle Seiten, die du in Notion für «ConfluenceSync» freigegeben hast.",
    "demo": "Beispielnotizen zum Ausprobieren. Doppelklick auf eine Seite öffnet die Vorschau.",
}


def when(node: SourceNode) -> str:
    return node.edited_at.astimezone().strftime("%d.%m.%Y %H:%M") if node.edited_at else ""


class SourcesPage(Page):
    title = "Notizen"
    subtitle = "Wähle eine Seite aus. Du siehst zuerst eine Vorschau, bevor etwas veröffentlicht wird."

    def __init__(self, win):
        super().__init__(win, scroll=False)
        self.source = ""
        self.loaded_for: str | None = None
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.body.addWidget(self.tabs)

        self.hint = label("", "muted")
        self.body.addWidget(self.hint)
        self.not_connected = QWidget()
        nc = QVBoxLayout(self.not_connected)
        nc.setContentsMargins(0, 0, 0, 0)
        self.nc_note = Note("warn", "")
        nc.addWidget(self.nc_note)
        nc.addLayout(hbox(button("Jetzt verbinden", "primary", lambda: self.win.go("connections")), None))
        self.body.addWidget(self.not_connected)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Seiten suchen …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self.reload_btn = button("↻ Neu laden", None, self.reload)
        self.preview_btn = button("Vorschau anzeigen →", "primary", self._open_selected)
        self.preview_btn.setEnabled(False)
        self.toolbar = QWidget()
        self.toolbar.setLayout(hbox(self.search, self.reload_btn, self.preview_btn))
        self.search.setMinimumWidth(320)
        self.body.addWidget(self.toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Titel", "Zuletzt geändert", "In Confluence"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(22)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemDoubleClicked.connect(self._double_click)
        self.tree.itemSelectionChanged.connect(self._selection)
        self.body.addWidget(self.tree, 1)
        self.message = Note("info", "")
        self.message.hide()
        self.body.addWidget(self.message)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self._search)

    # ------------------------------------------------------------------ show

    def on_show(self, **kwargs) -> None:
        sources = self.services.sources()
        if self.tabs.count() != len(sources):
            self.tabs.blockSignals(True)
            while self.tabs.count():
                self.tabs.removeTab(0)
            for key, name in sources:
                index = self.tabs.addTab(name)
                self.tabs.setTabData(index, key)
            self.tabs.blockSignals(False)
            self.tabs.setCurrentIndex(self._preferred_tab())
        self._tab_changed(self.tabs.currentIndex(), force=False)

    def _preferred_tab(self) -> int:
        st = self.services.status()
        for i in range(self.tabs.count()):
            key = self.tabs.tabData(i)
            if (key == "onenote" and st.onenote_account) or (key == "notion" and st.notion_connected):
                return i
        return 0

    def _tab_changed(self, index: int, force: bool = True) -> None:
        self.source = self.tabs.tabData(index) or ""
        self.hint.setText(HINTS.get(self.source, ""))
        st = self.services.status()
        connected = {"demo": True, "onenote": bool(st.onenote_account), "notion": st.notion_connected}[self.source]
        if not connected:
            text = {"onenote": "OneNote ist noch nicht verbunden. Du brauchst dafür die Client-ID und Tenant-ID "
                               "von deiner IT – die Anleitung unter «Verbindungen» hilft dir.",
                    "notion": "Notion ist noch nicht verbunden. Unter «Verbindungen» kannst du in zwei Minuten "
                              "einen Token erstellen und eintragen."}[self.source]
            self.nc_note.set("warn", text)
        if not st.confluence_connected and connected:
            self.message.set("warn", "Confluence ist noch nicht verbunden. Du kannst Notizen ansehen, aber für die "
                                     "Vorschau braucht es die Verbindung zu Confluence.")
            self.message.show()
        else:
            self.message.hide()
        self.not_connected.setVisible(not connected)
        self.toolbar.setVisible(connected)
        self.tree.setVisible(connected)
        if connected and (force or self.loaded_for != self.source):
            self.reload()

    # ------------------------------------------------------------------ loading

    def reload(self) -> None:
        self.loaded_for = self.source
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.tree.clear()
        self._placeholder(self.tree.invisibleRootItem(), "Wird geladen …")
        self._load(self.tree.invisibleRootItem(), None)

    def _placeholder(self, parent: QTreeWidgetItem, text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.UserRole, LOADING)
        item.setForeground(0, Qt.gray)
        item.setFlags(Qt.ItemIsEnabled)
        parent.addChild(item)
        return item

    def _load(self, parent: QTreeWidgetItem, node_id: str | None) -> None:
        source = self.source

        def done(nodes: list[SourceNode]) -> None:
            if source != self.source:
                return
            self._fill(parent, nodes)

        def failed(message: str) -> None:
            if source != self.source:
                return
            self._clear_children(parent)
            self._placeholder(parent, "⚠ " + message)

        run_task(self.services.children, source, node_id, on_done=done, on_error=failed)

    def _clear_children(self, parent: QTreeWidgetItem) -> None:
        for i in reversed(range(parent.childCount())):
            parent.removeChild(parent.child(i))

    def _fill(self, parent: QTreeWidgetItem, nodes: list[SourceNode]) -> None:
        self._clear_children(parent)
        published = self.services.published_ids(self.source)
        if not nodes:
            text = ("Keine freigegebenen Seiten gefunden. Gib Seiten in Notion über ••• → Verbindungen frei."
                    if self.source == "notion" and parent is self.tree.invisibleRootItem() else "Leer")
            self._placeholder(parent, text)
            return
        for node in nodes:
            item = QTreeWidgetItem([f"{ICONS.get(node.kind, '📄')}  {node.title}", when(node),
                                    "✓ veröffentlicht" if node.kind == "page" and node.id in published else ""])
            item.setData(0, Qt.UserRole, node.model_dump(mode="json"))
            item.setForeground(2, Qt.darkGreen)
            if node.has_children and node.kind != "page":
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                self._placeholder(item, "Wird geladen …")
            if node.kind != "page":
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            parent.addChild(item)
        if parent is self.tree.invisibleRootItem() and parent.childCount() == 1:
            parent.child(0).setExpanded(True)

    def _expand(self, item: QTreeWidgetItem) -> None:
        if item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == LOADING:
            node = item.data(0, Qt.UserRole)
            if isinstance(node, dict):
                self._load(item, node["id"])

    # ------------------------------------------------------------------ search

    def _search(self) -> None:
        query = self.search.text().strip()
        if self.source == "notion":
            if not query:
                self.reload()
                return
            self.tree.clear()
            self._placeholder(self.tree.invisibleRootItem(), "Suche läuft …")
            source = self.source
            run_task(self.services.search, source, query,
                     on_done=lambda nodes: source == self.source and self._fill(self.tree.invisibleRootItem(), nodes),
                     on_error=lambda m: self._fill(self.tree.invisibleRootItem(), []))
            return
        self._filter(self.tree.invisibleRootItem(), query.lower())

    def _filter(self, parent: QTreeWidgetItem, query: str) -> bool:
        """Hide loaded items that don't match. Returns True if something below matches."""
        any_visible = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.UserRole) == LOADING:
                child.setHidden(bool(query))
                continue
            below = self._filter(child, query)
            match = not query or query in child.text(0).lower() or below
            child.setHidden(not match)
            if query and below:
                child.setExpanded(True)
            any_visible |= match
        return any_visible

    # ------------------------------------------------------------------ open

    def _node(self, item: QTreeWidgetItem | None) -> dict | None:
        data = item.data(0, Qt.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _selection(self) -> None:
        node = self._node(self.tree.currentItem())
        self.preview_btn.setEnabled(bool(node and node["kind"] == "page"))

    def _double_click(self, item: QTreeWidgetItem) -> None:
        node = self._node(item)
        if node and node["kind"] == "page":
            self.win.go("preview", source=self.source, source_id=node["id"])

    def _open_selected(self) -> None:
        self._double_click(self.tree.currentItem())
