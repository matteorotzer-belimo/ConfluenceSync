"""Reusable widgets: cards, notes, help boxes, badges, connection forms and the target picker."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from ..services import Services
from .style import NOTE_STYLES, STATUS_STYLES
from .worker import run_task

CONFLUENCE_PLACEHOLDER = "https://confluence.example.com"
TOKEN_PAGE = "/plugins/personalaccesstokens/usertokens.action"
NOTION_INTEGRATIONS = "https://www.notion.so/my-integrations"

IT_REQUEST = """Bitte eine App-Registrierung in Microsoft Entra ID anlegen:
- Name: ConfluenceSync
- Unterstützte Kontotypen: nur Konten in diesem Organisationsverzeichnis
- Plattform: «Mobile und Desktopanwendungen», Umleitungs-URI: http://localhost
- «Öffentliche Clientflows zulassen»: Ja (kein Client-Geheimnis nötig)
- API-Berechtigungen (Microsoft Graph, delegiert): Notes.Read, User.Read
- Falls nötig: Administratorzustimmung erteilen
Danach bitte die Anwendungs-ID (Client-ID) und die Verzeichnis-ID (Tenant-ID) mitteilen.
ConfluenceSync liest OneNote nur im Namen der angemeldeten Person (nur lesen)."""


# --------------------------------------------------------------------------- small helpers


def label(text: str = "", name: str | None = None, rich: bool = False, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    lbl.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if rich:
        lbl.setOpenExternalLinks(True)
        lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
    return lbl


def button(text: str, kind: str | None = None, on_click=None) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setObjectName(kind)
    btn.setCursor(Qt.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def hbox(*widgets, spacing: int = 10, stretch_first: bool = False) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(spacing)
    row.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        if widget is None:
            row.addStretch(1)
        elif isinstance(widget, QWidget):
            row.addWidget(widget)
        else:
            row.addLayout(widget)
    return row


def steps_html(steps: list[str]) -> str:
    items = "".join(f'<li style="margin-bottom:6px">{s}</li>' for s in steps)
    return f'<ol style="margin-left:-18px">{items}</ol>'


def ui(text: str) -> str:
    """Marks a button or menu name in instructions."""
    return f'<b style="color:#1d2433">«{escape(text)}»</b>'


def open_url(url: str) -> None:
    if url.startswith(("http://", "https://")):
        QDesktopServices.openUrl(QUrl(url))


def confirm(parent: QWidget, title: str, text: str, yes: str, no: str = "Abbrechen", danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    ok = box.addButton(yes, QMessageBox.AcceptRole)
    box.addButton(no, QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is ok


def clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout():
            clear(item.layout())


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: int = 22, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)

    def add(self, item):
        if isinstance(item, QWidget):
            self.body.addWidget(item)
        else:
            self.body.addLayout(item)
        return item


class Note(QFrame):
    """Coloured hint box. `html` is trusted, app-made rich text."""

    def __init__(self, kind: str, html: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.text = QLabel()
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignTop)
        self.icon.setStyleSheet("font-size: 13pt; background: transparent; border: none;")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        self.text.setOpenExternalLinks(True)
        self.text.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(10)
        row.addWidget(self.icon)
        row.addWidget(self.text, 1)
        self.set(kind, html)

    def set(self, kind: str, html: str) -> None:
        bg, border, icon = NOTE_STYLES[kind]
        self.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 10px; }}")
        self.icon.setText(icon)
        self.text.setText(html)

    def set_plain(self, kind: str, text: str) -> None:
        self.set(kind, escape(text).replace("\n", "<br>"))


class HelpBox(QWidget):
    """Collapsible «How do I find this?» section."""

    def __init__(self, title: str, content: QWidget | str, expanded: bool = False):
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setObjectName("helpToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setCursor(Qt.PointingHandCursor)
        if isinstance(content, str):
            content = label(content, rich=True)
        self.content = content
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        self.toggle.toggled.connect(self._update)
        self._update(expanded)

    def _update(self, expanded: bool) -> None:
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)


class Badge(QLabel):
    def __init__(self, status: str = "unknown", text: str = ""):
        super().__init__()
        self.set(status, text)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, status: str, text: str) -> None:
        bg, fg = STATUS_STYLES.get(status, STATUS_STYLES["unknown"])
        self.setText(f"●  {text}")
        self.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 10px; padding: 3px 10px; "
                           "font-weight: 600; font-size: 9pt;")


class StatusLine(QWidget):
    def __init__(self):
        super().__init__()
        self.dot = QLabel("●")
        self.text = QLabel()
        self.text.setWordWrap(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.dot)
        row.addWidget(self.text, 1)

    def set(self, ok: bool | None, text: str) -> None:
        colour = {True: "#22c55e", False: "#9aa1b0", None: "#f59e0b"}[ok]
        self.dot.setStyleSheet(f"color: {colour}; font-size: 12pt;")
        self.text.setText(text)


def field(title: str, widget: QWidget, hint: str | None = None) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(5)
    head = label(title)
    head.setStyleSheet("font-weight: 600;")
    col.addWidget(head)
    col.addWidget(widget)
    if hint:
        col.addWidget(label(hint, "muted", rich=True))
    return col


class SecretEdit(QWidget):
    """Password field with a show/hide button."""

    def __init__(self, placeholder: str = ""):
        super().__init__()
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self.show_btn = button("Anzeigen", "ghost", self._toggle)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.edit, 1)
        row.addWidget(self.show_btn)

    def _toggle(self) -> None:
        hidden = self.edit.echoMode() == QLineEdit.Password
        self.edit.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self.show_btn.setText("Verbergen" if hidden else "Anzeigen")

    def text(self) -> str:
        return self.edit.text().strip()

    def clear(self) -> None:
        self.edit.clear()


# --------------------------------------------------------------------------- connection forms


class BusyMixin:
    def busy(self, on: bool, buttons: list[QPushButton], text: str | None = None) -> None:
        for btn in buttons:
            btn.setEnabled(not on)
        if on and text:
            self.result.set("info", f"⏳ {escape(text)}")
            self.result.show()


class ConfluenceForm(QWidget, BusyMixin):
    changed = Signal()

    def __init__(self, services: Services, compact: bool = False):
        super().__init__()
        self.services = services
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.status = StatusLine()
        layout.addWidget(self.status)
        self.url = QLineEdit()
        self.url.setPlaceholderText(CONFLUENCE_PLACEHOLDER)
        layout.addLayout(field("Adresse von Confluence", self.url,
                               "Die Adresse, die im Browser oben steht, wenn du Confluence öffnest "
                               "(nur der Anfang, z. B. <i>https://confluence.firma.ch</i>)."))
        self.token = SecretEdit("Persönlichen Zugriffstoken hier einfügen")
        layout.addLayout(field("Persönlicher Zugriffstoken (PAT)", self.token,
                               "Wird sicher im Windows-Anmeldeinformationsspeicher abgelegt, nie in einer Datei."))
        self.connect_btn = button("Verbinden und testen", "primary", self._connect)
        self.token_page_btn = button("Token-Seite in Confluence öffnen", None, self._open_token_page)
        self.disconnect_btn = button("Trennen", "danger", self._disconnect)
        layout.addLayout(hbox(self.connect_btn, self.token_page_btn, None, self.disconnect_btn))
        self.result = Note("info", "")
        self.result.hide()
        layout.addWidget(self.result)
        help_html = steps_html([
            "Öffne Confluence im Browser und melde dich an.",
            f"Klicke oben rechts auf dein Profilbild und wähle {ui('Einstellungen')} (oder {ui('Profil')}).",
            f"Wähle links {ui('Persönliche Zugriffstoken')} und dann {ui('Token erstellen')}.",
            f"Gib als Name <i>ConfluenceSync</i> ein. Ablaufdatum gemäss Vorgabe deiner Firma. Klicke {ui('Erstellen')}.",
            "Kopiere den Token sofort. Er wird nur ein einziges Mal angezeigt.",
            "Füge ihn hier oben ein und klicke auf «Verbinden und testen».",
        ]) + ('<p style="color:#7a8396">Tipp: Mit «Token-Seite in Confluence öffnen» springst du direkt zu '
              "Schritt 3. Die App kann nur dort schreiben, wo du auch selbst Rechte hast.</p>")
        layout.addWidget(HelpBox("Wo finde ich den Token?", help_html, expanded=not compact))
        self.refresh()

    def refresh(self) -> None:
        st = self.services.status(check_onenote=False)
        if st.confluence_url and not self.url.text():
            self.url.setText(st.confluence_url)
        if st.confluence_connected:
            who = f" als {st.confluence_user}" if st.confluence_user else ""
            self.status.set(True, f"Verbunden mit {st.confluence_url}{who}")
            self.token.edit.setPlaceholderText("Gespeichert. Nur ausfüllen, wenn du einen neuen Token hast.")
        else:
            self.status.set(False, "Noch nicht verbunden")
            self.token.edit.setPlaceholderText("Persönlichen Zugriffstoken hier einfügen")
        self.disconnect_btn.setVisible(st.confluence_connected)

    def _open_token_page(self) -> None:
        url = self.url.text().strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            self.result.set("warn", "Bitte zuerst die Adresse von Confluence eingeben (beginnt mit https://).")
            self.result.show()
            return
        open_url(url + TOKEN_PAGE)

    def _connect(self) -> None:
        buttons = [self.connect_btn, self.disconnect_btn]
        self.busy(True, buttons, "Verbindung wird getestet …")

        def done(name: str) -> None:
            self.busy(False, buttons)
            self.token.clear()
            self.result.set("ok", f"<b>Verbindung klappt.</b> Angemeldet als {escape(name or 'unbekannt')}.")
            self.refresh()
            self.changed.emit()

        def failed(message: str) -> None:
            self.busy(False, buttons)
            self.result.set_plain("err", message)

        run_task(self.services.connect_confluence, self.url.text(), self.token.text(), on_done=done, on_error=failed)

    def _disconnect(self) -> None:
        if not confirm(self, "Confluence trennen", "Der gespeicherte Token wird von diesem Laptop gelöscht. "
                       "Deine Seiten in Confluence bleiben bestehen.", "Trennen", danger=True):
            return
        self.services.disconnect_confluence()
        self.result.set("info", "Confluence wurde getrennt.")
        self.result.show()
        self.refresh()
        self.changed.emit()


class OneNoteForm(QWidget, BusyMixin):
    changed = Signal()

    def __init__(self, services: Services, compact: bool = False):
        super().__init__()
        self.services = services
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.status = StatusLine()
        layout.addWidget(self.status)
        layout.addWidget(Note("accent", "Für OneNote braucht ConfluenceSync eine <b>App-Registrierung</b> deiner "
                                        "Firma bei Microsoft. Die IT gibt dir dafür zwei Nummern: die "
                                        "<b>Client-ID</b> und die <b>Tenant-ID</b>. Das machst du nur einmal."))
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("z. B. 1a2b3c4d-1111-2222-3333-444455556666")
        self.tenant_id = QLineEdit()
        self.tenant_id.setPlaceholderText("organizations")
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addLayout(field("Client-ID (Anwendungs-ID)", self.client_id))
        row.addLayout(field("Tenant-ID (Verzeichnis-ID)", self.tenant_id,
                            "Leer lassen, wenn die IT nichts angegeben hat."))
        layout.addLayout(row)
        self.login_btn = button("Speichern und bei Microsoft anmelden", "primary", self._login)
        self.logout_btn = button("Abmelden", "danger", self._logout)
        layout.addLayout(hbox(self.login_btn, None, self.logout_btn))
        self.result = Note("info", "")
        self.result.hide()
        layout.addWidget(self.result)

        it_box = QFrame()
        it_box.setObjectName("itBox")
        it_layout = QVBoxLayout(it_box)
        it_layout.setContentsMargins(16, 14, 16, 14)
        it_layout.addWidget(label("Text für deine IT (zum Kopieren)", "h3"))
        it_text = label(IT_REQUEST)
        it_text.setStyleSheet("font-family: Consolas; font-size: 9pt; color: #4a5468;")
        it_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        it_layout.addWidget(it_text)
        self.copy_btn = button("Text kopieren", None, self._copy)
        it_layout.addLayout(hbox(self.copy_btn, None))
        layout.addWidget(HelpBox("Was muss die IT einrichten?", it_box, expanded=not compact))
        login_help = steps_html([
            "Trage Client-ID und Tenant-ID ein, die du von der IT bekommen hast.",
            "Klicke auf «Speichern und bei Microsoft anmelden». Dein Browser öffnet sich.",
            "Melde dich mit deinem Firmenkonto an und bestätige, dass ConfluenceSync deine Notizen <b>lesen</b> darf.",
            "Wechsle zurück in die App. Die Anmeldung bleibt gespeichert (verschlüsselt auf diesem Laptop).",
        ])
        layout.addWidget(HelpBox("Wie funktioniert die Anmeldung?", login_help, expanded=False))
        self.refresh()

    def refresh(self, status=None) -> None:
        s = self.services.config
        if not self.client_id.text():
            self.client_id.setText(s.ms_client_id)
        if not self.tenant_id.text() and s.ms_tenant_id != "organizations":
            self.tenant_id.setText(s.ms_tenant_id)
        st = status or self.services.status()
        if st.onenote_account:
            self.status.set(True, f"Angemeldet als {st.onenote_account}")
        elif st.onenote_configured:
            self.status.set(None, "IDs gespeichert, aber noch nicht angemeldet")
        else:
            self.status.set(False, "Noch nicht eingerichtet")
        self.logout_btn.setVisible(bool(st.onenote_account))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(IT_REQUEST)
        self.copy_btn.setText("Kopiert ✓")
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Text kopieren"))

    def _login(self) -> None:
        try:
            self.services.configure_onenote(self.client_id.text(), self.tenant_id.text())
        except Exception as exc:  # noqa: BLE001 - UserError
            self.result.set_plain("err", str(exc))
            self.result.show()
            return
        buttons = [self.login_btn, self.logout_btn]
        self.busy(True, buttons, "Dein Browser hat sich geöffnet. Bitte dort mit dem Firmenkonto anmelden "
                                 "und danach hierher zurückkehren …")

        def done(account: str) -> None:
            self.busy(False, buttons)
            self.result.set("ok", f"<b>Angemeldet.</b> {escape(account)} – deine Notizbücher sind jetzt sichtbar.")
            self.refresh()
            self.changed.emit()

        def failed(message: str) -> None:
            self.busy(False, buttons)
            self.result.set_plain("err", message)
            self.refresh()

        run_task(self.services.login_onenote, on_done=done, on_error=failed)

    def _logout(self) -> None:
        self.services.logout_onenote()
        self.result.set("info", "Abgemeldet. Die gespeicherte Anmeldung wurde gelöscht.")
        self.result.show()
        self.refresh()
        self.changed.emit()


class NotionForm(QWidget, BusyMixin):
    changed = Signal()

    def __init__(self, services: Services, compact: bool = False):
        super().__init__()
        self.services = services
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.status = StatusLine()
        layout.addWidget(self.status)
        self.token = SecretEdit("Integrations-Token hier einfügen (beginnt mit ntn_ oder secret_)")
        layout.addLayout(field("Notion-Integrations-Token", self.token,
                               "Wird sicher im Windows-Anmeldeinformationsspeicher abgelegt."))
        self.connect_btn = button("Verbinden und testen", "primary", self._connect)
        self.open_btn = button("Notion-Integrationen öffnen", None, lambda: open_url(NOTION_INTEGRATIONS))
        self.disconnect_btn = button("Trennen", "danger", self._disconnect)
        layout.addLayout(hbox(self.connect_btn, self.open_btn, None, self.disconnect_btn))
        self.result = Note("info", "")
        self.result.hide()
        layout.addWidget(self.result)
        help_html = steps_html([
            f"Klicke auf «Notion-Integrationen öffnen» und melde dich bei Notion an.",
            f"Klicke auf {ui('Neue Integration')}. Name: <i>ConfluenceSync</i>, Typ: {ui('Intern')}, "
            "Workspace: deiner.",
            f"Unter {ui('Funktionen')} reicht {ui('Inhalte lesen')}. Speichern.",
            f"Kopiere den {ui('Internen Integrations-Token')} und füge ihn hier ein.",
            f"<b>Wichtig:</b> Gib in Notion jede Seite frei, die du veröffentlichen möchtest: Seite öffnen → "
            f"oben rechts {ui('•••')} → {ui('Verbindungen')} → <i>ConfluenceSync</i>. Unterseiten sind dann automatisch dabei.",
        ])
        layout.addWidget(HelpBox("Wo finde ich den Token?", help_html, expanded=not compact))
        self.refresh()

    def refresh(self) -> None:
        if self.services.status(check_onenote=False).notion_connected:
            self.status.set(True, "Verbunden")
            self.token.edit.setPlaceholderText("Gespeichert. Nur ausfüllen, wenn du einen neuen Token hast.")
            self.disconnect_btn.show()
        else:
            self.status.set(False, "Noch nicht verbunden")
            self.disconnect_btn.hide()

    def _connect(self) -> None:
        token = self.token.text()
        if not token and self.services.status(check_onenote=False).notion_connected:
            run_task(self.services.test_notion, on_done=lambda info: self._ok(info),
                     on_error=lambda m: self.result.set_plain("err", m))
            return
        buttons = [self.connect_btn, self.disconnect_btn]
        self.busy(True, buttons, "Verbindung wird getestet …")

        def failed(message: str) -> None:
            self.busy(False, buttons)
            self.result.set_plain("err", message)

        def done(info: dict) -> None:
            self.busy(False, buttons)
            self.token.clear()
            self._ok(info)

        run_task(self.services.connect_notion, token, on_done=done, on_error=failed)

    def _ok(self, info: dict) -> None:
        name = (info or {}).get("workspace") or (info or {}).get("name") or ""
        where = f" mit {escape(name)}" if name else ""
        self.result.set("ok", f"<b>Verbindung klappt</b>{where}. Denk daran, die gewünschten Seiten in "
                              "Notion für «ConfluenceSync» freizugeben.")
        self.result.show()
        self.refresh()
        self.changed.emit()

    def _disconnect(self) -> None:
        self.services.disconnect_notion()
        self.result.set("info", "Notion wurde getrennt.")
        self.result.show()
        self.refresh()
        self.changed.emit()


# --------------------------------------------------------------------------- target picker


class TargetPicker(QWidget):
    """Choose the Confluence space and (optionally) the parent page."""

    changed = Signal()
    TOP = "— Oberste Ebene im Space —"

    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self.parent_id = ""
        self.parent_title = ""
        self._loaded = False
        self._pending_space = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.space = QComboBox()
        self.space.setMinimumWidth(200)
        self.space.currentIndexChanged.connect(self._space_changed)
        layout.addLayout(field("Space", self.space))
        head = label("Elternseite (optional)")
        head.setStyleSheet("font-weight: 600;")
        layout.addWidget(head)
        self.parent_label = label(self.TOP)
        self.parent_label.setStyleSheet("background: #fbfbfc; border: 1px solid #e3e6ec; border-radius: 8px; padding: 8px 10px;")
        self.change_btn = button("Ändern", None, self._toggle_search)
        layout.addLayout(hbox(self.parent_label, self.change_btn))
        self.parent_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Seitentitel suchen …")
        self.search.textChanged.connect(lambda: self._timer.start())
        self.results = QListWidget()
        self.results.setMaximumHeight(200)
        self.results.itemClicked.connect(self._pick)
        self.search.hide()
        self.results.hide()
        layout.addWidget(self.search)
        layout.addWidget(self.results)
        self.recent_box = QWidget()
        self.recent = QHBoxLayout(self.recent_box)
        self.recent.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.recent_box)
        self.message = label("", "muted")
        self.message.hide()
        layout.addWidget(self.message)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._run_search)

    # -- data

    def load(self, space: str = "", parent_id: str = "", parent_title: str = "") -> None:
        self._pending_space = space
        self.set_parent(parent_id, parent_title)
        self.message.setText("Spaces werden geladen …")
        self.message.show()

        def done(spaces: list[dict]) -> None:
            self.space.blockSignals(True)
            self.space.clear()
            self.space.addItem("Bitte wählen …", "")
            for item in spaces:
                text = (f"Persönlicher Bereich ({item['name']})" if item.get("personal")
                        else f"{item['name']}  ·  {item['key']}")
                self.space.addItem(text, item["key"])
            index = max(self.space.findData(self._pending_space), 0)
            self.space.setCurrentIndex(index)
            self.space.blockSignals(False)
            self._loaded = True
            self.message.hide()
            self._fill_recent()
            self.changed.emit()

        def failed(message: str) -> None:
            self.message.setText(message)
            self.message.show()

        run_task(self.services.spaces, on_done=done, on_error=failed)

    def value(self) -> dict:
        key = self.space.currentData() or ""
        name = self.space.currentText() if key else ""
        return {"space": key, "space_name": name, "parent_id": self.parent_id, "parent_title": self.parent_title}

    def set_parent(self, parent_id: str, title: str) -> None:
        self.parent_id = parent_id or ""
        self.parent_title = title or ""
        self.parent_label.setText(f"📄 {title}" if parent_id else self.TOP)
        self.changed.emit()

    # -- events

    def _space_changed(self) -> None:
        self.set_parent("", "")
        self.search.clear()
        self.results.clear()
        self.changed.emit()

    def _toggle_search(self) -> None:
        show = not self.search.isVisible()
        if show and not self.space.currentData():
            self.message.setText("Bitte zuerst einen Space wählen.")
            self.message.show()
            return
        self.search.setVisible(show)
        self.results.setVisible(show)
        self.change_btn.setText("Schliessen" if show else "Ändern")
        if show:
            self.search.setFocus()
            self._run_search()

    def _run_search(self) -> None:
        space = self.space.currentData()
        if not space:
            return
        query = self.search.text()

        def done(pages: list[dict]) -> None:
            if query != self.search.text():
                return
            self.results.clear()
            top = QListWidgetItem(self.TOP)
            top.setData(Qt.UserRole, ("", ""))
            self.results.addItem(top)
            for page in pages:
                text = page["title"] + (f"\n   {page['path']}" if page.get("path") else "")
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, (page["id"], page["title"]))
                self.results.addItem(item)
            if not pages:
                self.results.addItem(QListWidgetItem("Keine passende Seite gefunden."))

        run_task(self.services.search_pages, space, query, on_done=done,
                 on_error=lambda m: (self.message.setText(m), self.message.show()))

    def _pick(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data is None:
            return
        self.set_parent(*data)
        self._toggle_search()

    def _fill_recent(self) -> None:
        clear(self.recent)
        recent = [r for r in self.services.config.recent_parents if r.get("id")][:4]
        if not recent:
            self.recent_box.hide()
            return
        self.recent.addWidget(label("Zuletzt:", "muted", wrap=False))
        for entry in recent:
            chip = button(entry.get("title") or entry.get("space"), "ghost")
            chip.setToolTip(f"{entry.get('space_name') or entry.get('space')} / {entry.get('title')}")
            chip.clicked.connect(lambda _=False, e=entry: self._use_recent(e))
            self.recent.addWidget(chip)
        self.recent.addStretch(1)
        self.recent_box.show()

    def _use_recent(self, entry: dict) -> None:
        index = self.space.findData(entry.get("space"))
        if index >= 0:
            self.space.setCurrentIndex(index)
        self.set_parent(entry.get("id", ""), entry.get("title", ""))
