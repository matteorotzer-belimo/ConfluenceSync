"""Guided first steps, like a short tutorial. Can be restarted at any time from the sidebar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from .page import Page
from .widgets import (Badge, Card, ConfluenceForm, Note, NotionForm, OneNoteForm, TargetPicker,
                      button, label, steps_html, ui)

STEPS = ["Willkommen", "Confluence verbinden", "Ziel wählen", "Notizen verbinden", "Erste Seite veröffentlichen"]


def tile(icon: str, title: str, text: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("tile")
    col = QVBoxLayout(frame)
    col.setContentsMargins(16, 16, 16, 16)
    col.setSpacing(6)
    big = label(icon)
    big.setStyleSheet("font-size: 22pt; border: none; background: transparent;")
    col.addWidget(big)
    head = label(title, "h3")
    head.setStyleSheet("border: none; background: transparent;")
    col.addWidget(head)
    body = label(text, "muted")
    body.setStyleSheet("border: none; background: transparent;")
    col.addWidget(body)
    col.addStretch(1)
    return frame


class TutorialPage(Page):
    title = "Anleitung"
    subtitle = "In fünf kurzen Schritten bist du startklar. Du kannst die Anleitung jederzeit wieder öffnen."

    def __init__(self, win):
        super().__init__(win)
        self.index = 0
        row = QHBoxLayout()
        row.setSpacing(24)
        self.body.addLayout(row)

        # step list on the left
        side = QVBoxLayout()
        side.setSpacing(4)
        self.step_buttons = QButtonGroup(self)
        self.step_buttons.setExclusive(True)
        for i, name in enumerate(STEPS):
            btn = QPushButton(f"  {i + 1}   {name}")
            btn.setObjectName("step")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, n=i: self.show_step(n))
            self.step_buttons.addButton(btn, i)
            side.addWidget(btn)
        side.addStretch(1)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(250)
        row.addWidget(side_widget, 0, Qt.AlignTop)

        # content card on the right
        self.card = Card(margins=30, spacing=14)
        row.addWidget(self.card, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(STEPS))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.card.add(self.progress)
        self.steps: list[QWidget] = [self._welcome(), self._confluence(), self._target(), self._source(),
                                     self._finish()]
        for step in self.steps:
            step.hide()
            self.card.add(step)

        nav = QFrame()
        nav.setStyleSheet("QFrame { border-top: 1px solid #eef0f4; }")
        nav_row = QHBoxLayout(nav)
        nav_row.setContentsMargins(0, 16, 0, 0)
        self.back_btn = button("← Zurück", "ghost", lambda: self.show_step(self.index - 1))
        self.skip_btn = button("Anleitung überspringen", "ghost", self._skip)
        self.next_btn = button("Weiter →", "primary", self._next)
        self.next_btn.setMinimumWidth(150)
        nav_row.addWidget(self.back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.skip_btn)
        nav_row.addWidget(self.next_btn)
        self.card.add(nav)
        self.body.addStretch(1)

    # ------------------------------------------------------------------ steps

    def _step(self, title: str, lead: str) -> tuple[QWidget, QVBoxLayout]:
        widget = QWidget()
        col = QVBoxLayout(widget)
        col.setContentsMargins(0, 6, 0, 0)
        col.setSpacing(14)
        col.addWidget(label(title, "h2"))
        col.addWidget(label(lead, "lead", rich=True))
        return widget, col

    def _welcome(self) -> QWidget:
        widget, col = self._step(
            "Willkommen bei ConfluenceSync 👋",
            "Mit ConfluenceSync machst du aus deinen Notizen in OneNote oder Notion saubere Confluence-Seiten. "
            "Ohne Kopieren und Einfügen, ohne Formatierungschaos.")
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(tile("🔌", "1. Konten verbinden", "Einmalig Confluence und deine Notizen-App verbinden. "
                                                         "Die Anleitung zeigt dir genau, wo du was findest."), 0, 0)
        grid.addWidget(tile("👀", "2. Vorschau prüfen", "Notiz auswählen und ansehen, wie die Seite in "
                                                       "Confluence aussehen wird."), 0, 1)
        grid.addWidget(tile("🚀", "3. Veröffentlichen", "Mit einem Klick veröffentlichen. Später aktualisierst "
                                                       "du die Seite genauso einfach."), 0, 2)
        col.addLayout(grid)
        col.addWidget(Note("info", "<b>Deine Zugangsdaten bleiben auf diesem Laptop.</b> Tokens werden im "
                                   "Windows-Anmeldeinformationsspeicher abgelegt, nicht in Dateien. "
                                   "ConfluenceSync schreibt nur nach Confluence, deine Notizen werden nie verändert."))
        if self.services.demo:
            col.addWidget(Note("accent", "<b>Demo-Modus:</b> Confluence wird nur simuliert. Gib eine beliebige "
                                         "Adresse (z. B. https://confluence.example.com) und irgendeinen Text als "
                                         "Token ein. Als Notizen stehen Beispielseiten bereit."))
        col.addStretch(1)
        return widget

    def _confluence(self) -> QWidget:
        widget, col = self._step(
            "Schritt 2: Confluence verbinden",
            "ConfluenceSync meldet sich mit deinem <b>persönlichen Zugriffstoken</b> bei Confluence an. "
            "Das ist wie ein Passwort nur für diese App, das du jederzeit wieder löschen kannst.")
        self.confluence_form = ConfluenceForm(self.services)
        self.confluence_form.changed.connect(self.win.refresh_status)
        col.addWidget(self.confluence_form)
        col.addStretch(1)
        return widget

    def _target(self) -> QWidget:
        widget, col = self._step(
            "Schritt 3: Wohin sollen deine Seiten?",
            "Wähle den Space und – wenn du möchtest – eine Elternseite, unter der neue Seiten erscheinen. "
            "Du kannst das bei jeder Veröffentlichung noch ändern.")
        self.target_note = Note("warn", "Bitte zuerst Confluence verbinden (Schritt 2).")
        col.addWidget(self.target_note)
        self.target = TargetPicker(self.services)
        col.addWidget(self.target)
        col.addWidget(Note("info", "Wähle einen Ort, an dem du Seiten erstellen darfst – zum Beispiel deinen "
                                   "<b>persönlichen Bereich</b> zum Ausprobieren."))
        col.addStretch(1)
        return widget

    def _source(self) -> QWidget:
        widget, col = self._step(
            "Schritt 4: Woher kommen deine Notizen?",
            "Verbinde die App, in der du deine Notizen schreibst. Du kannst auch beide verbinden.")
        choice = QHBoxLayout()
        choice.setSpacing(14)
        self.choice_group = QButtonGroup(self)
        for i, (title, text) in enumerate([
            ("🟪  OneNote", "Mit deinem Firmenkonto.\nBraucht einmalig eine Freigabe der IT."),
            ("⬛  Notion", "Über eine eigene Integration.\nSofort einsatzbereit."),
        ]):
            btn = QPushButton(f"{title}\n{text}")
            btn.setObjectName("choice")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(74)
            self.choice_group.addButton(btn, i)
            choice.addWidget(btn)
        col.addLayout(choice)
        self.onenote_form = OneNoteForm(self.services)
        self.notion_form = NotionForm(self.services)
        for form in (self.onenote_form, self.notion_form):
            form.changed.connect(self.win.refresh_status)
            col.addWidget(form)
        # show/hide instead of a QStackedWidget: hidden forms take no space
        self.choice_group.idClicked.connect(self._show_source_form)
        self.choice_group.button(0).setChecked(True)
        self._show_source_form(0)
        if self.services.demo:
            col.addWidget(Note("accent", "Im Demo-Modus kannst du diesen Schritt überspringen und die "
                                         "Beispielnotizen verwenden."))
        col.addStretch(1)
        return widget

    def _finish(self) -> QWidget:
        widget, col = self._step(
            "Schritt 5: Deine erste Seite veröffentlichen 🎉",
            "Geschafft! So veröffentlichst du ab jetzt deine Notizen:")
        self.summary = Note("ok", "")
        col.addWidget(self.summary)
        col.addWidget(label(steps_html([
            f"Öffne links {ui('Notizen')}.",
            "Klappe dein Notizbuch und den Abschnitt auf und wähle eine Seite (Doppelklick).",
            "Prüfe die <b>Vorschau</b>: So wird die Seite in Confluence aussehen. Kontrolliere Space und Elternseite.",
            f"Klicke auf {ui('In Confluence veröffentlichen')}. Fertig!",
            f"Hast du die Notiz später geändert? Unter {ui('Meine Veröffentlichungen')} siehst du das und "
            f"klickst auf {ui('Aktualisieren')}.",
        ]), rich=True))
        col.addWidget(label("Was die Status bedeuten", "h3"))
        legend = QGridLayout()
        legend.setHorizontalSpacing(14)
        legend.setVerticalSpacing(8)
        for i, (status, text, explain) in enumerate([
            ("synced", "Aktuell", "Confluence zeigt den neusten Stand deiner Notiz."),
            ("source_changed", "Quelle geändert", "Du hast die Notiz geändert. Mit «Aktualisieren» übernehmen."),
            ("confluence_changed", "In Confluence geändert", "Jemand hat die Seite direkt in Confluence bearbeitet. "
                                                             "Du entscheidest, was gilt – nichts wird still überschrieben."),
            ("review", "Prüfung nötig", "Beide Seiten wurden geändert. Bitte die Vorschau ansehen und entscheiden."),
        ]):
            legend.addWidget(Badge(status, text), i, 0, Qt.AlignLeft)
            legend.addWidget(label(explain, "muted"), i, 1)
        legend.setColumnStretch(1, 1)
        col.addLayout(legend)
        col.addWidget(Note("info", "Wichtig: Änderungen bitte immer in der Notiz machen, nicht in Confluence. "
                                   "Jede erzeugte Seite trägt oben einen entsprechenden Hinweis."))
        col.addStretch(1)
        return widget

    # ------------------------------------------------------------------ navigation

    def on_show(self, step: int | None = None, **kwargs) -> None:
        self.show_step(0 if step is None else step)

    def _show_source_form(self, index: int) -> None:
        self.onenote_form.setVisible(index == 0)
        self.notion_form.setVisible(index == 1)

    def show_step(self, index: int) -> None:
        if self.index == 2 and index != 2:
            self._save_target()
        self.index = max(0, min(index, len(STEPS) - 1))
        for i, step in enumerate(self.steps):
            step.setVisible(i == self.index)
        if self.scroll_area is not None:
            self.scroll_area.verticalScrollBar().setValue(0)
        self.step_buttons.button(self.index).setChecked(True)
        self.progress.setValue(self.index + 1)
        self.back_btn.setVisible(self.index > 0)
        last = self.index == len(STEPS) - 1
        self.next_btn.setText("Erste Notiz auswählen →" if last else ("Los geht's →" if self.index == 0 else "Weiter →"))
        self.skip_btn.setVisible(not last)
        status = self.services.status(check_onenote=False)
        if self.index == 1:
            self.confluence_form.refresh()
        if self.index == 2:
            self.target_note.setVisible(not status.confluence_connected)
            self.target.setVisible(status.confluence_connected)
            if status.confluence_connected:
                s = self.services.config
                self.target.load(s.default_space, s.default_parent_id, s.default_parent_title)
        if self.index == 3:
            self.onenote_form.refresh()
            self.notion_form.refresh()
        if self.index == 4:
            self._fill_summary()

    def _fill_summary(self) -> None:
        st = self.services.status()
        s = self.services.config
        lines = [
            ("✅" if st.confluence_connected else "⬜") + " Confluence " +
            ("verbunden" if st.confluence_connected else "noch nicht verbunden"),
            ("✅" if st.any_source else "⬜") + " Notizen: " +
            (", ".join(n for n, ok in (("OneNote", st.onenote_account), ("Notion", st.notion_connected)) if ok)
             if st.any_source else ("Beispielnotizen (Demo)" if self.services.demo else "noch keine Quelle verbunden")),
            ("✅" if s.default_space else "⬜") + " Standard-Ziel: " +
            (f"{s.default_space_name or s.default_space}" + (f" / {s.default_parent_title}" if s.default_parent_title else "")
             if s.default_space else "noch keins (du wählst es beim Veröffentlichen)"),
        ]
        ready = st.confluence_connected and (st.any_source or self.services.demo)
        self.summary.set("ok" if ready else "warn", "<br>".join(lines) + (
            "" if ready else "<br><br>Was noch fehlt, kannst du jederzeit unter «Verbindungen» nachholen."))

    def _save_target(self) -> None:
        if not self.target._loaded:
            return
        value = self.target.value()
        if value["space"]:
            self.services.update_settings(default_space=value["space"], default_space_name=value["space_name"],
                                          default_parent_id=value["parent_id"],
                                          default_parent_title=value["parent_title"])

    def _next(self) -> None:
        if self.index == len(STEPS) - 1:
            self._done()
        else:
            self.show_step(self.index + 1)

    def _skip(self) -> None:
        self._save_target()
        self._done()

    def _done(self) -> None:
        self.services.update_settings(tutorial_completed=True)
        self.win.go("sources")
