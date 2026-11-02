"""«Verbindungen»: Confluence, OneNote and Notion in one place."""
from __future__ import annotations

from .page import Page
from .widgets import Card, ConfluenceForm, NotionForm, OneNoteForm, label


class ConnectionsPage(Page):
    title = "Verbindungen"
    subtitle = ("Hier verbindest du ConfluenceSync mit deinen Konten. Zugangsdaten werden sicher im "
                "Windows-Anmeldeinformationsspeicher abgelegt.")

    def __init__(self, win):
        super().__init__(win, max_width=900)
        self.forms = []
        for title, text, form in [
            ("Confluence", "Hierhin werden deine Seiten veröffentlicht.", ConfluenceForm(self.services, compact=True)),
            ("OneNote", "Notizen aus Microsoft OneNote (Firmenkonto).", OneNoteForm(self.services, compact=True)),
            ("Notion", "Seiten aus Notion, die du für die Integration freigegeben hast.",
             NotionForm(self.services, compact=True)),
        ]:
            card = Card(margins=24)
            card.add(label(title, "h2"))
            card.add(label(text, "muted"))
            card.add(form)
            form.changed.connect(self.win.refresh_status)
            self.forms.append(form)
            self.body.addWidget(card)
        self.body.addStretch(1)

    def on_show(self, **kwargs) -> None:
        for form in self.forms:
            form.refresh()
