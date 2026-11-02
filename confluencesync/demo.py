"""Developer demo mode: synthetic notes and an in-memory Confluence.

Started with `python -m confluencesync --demo`. Used for screenshots and UI tests without real
accounts. Not reachable from the normal app.
"""
from __future__ import annotations

import struct
import zlib
from datetime import datetime, timezone

from .confluence.checks import norm
from .confluence.client import ConfluenceError, Page
from .connectors.base import PageInfo, SourceError, SourceNode
from .connectors.onenote_html import parse_onenote_html
from .model import Image, SourceDocument

DEMO_BASE = "https://confluence.example.com"

PAGES = {
    "demo-besprechung": {
        "title": "Teamsitzung 28. Oktober",
        "section": "section:besprechungen",
        "edited": datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc),
        "html": """
<html><head><title>Teamsitzung 28. Oktober</title></head>
<body data-absolute-enabled="true">
<div style="position:absolute;left:48px;top:120px;width:640px">
  <h1>Ziele</h1>
  <p>Wir besprechen den <b>Stand der Auswertungen</b> und die nächsten Schritte für das
  <a href="https://example.com/projekt">Projekt</a>.</p>
  <ul><li>Dashboard für das Team bereitstellen</li><li>Datenquellen prüfen
    <ul><li>Export aus dem Ticketsystem</li><li>Archiv 2025</li></ul></li></ul>
  <h2>Aufgaben</h2>
  <p data-tag="to-do">Vorlage für Berichte erstellen</p>
  <p data-tag="to-do:completed">Termin mit der IT vereinbaren</p>
  <p data-tag="important">Freigabe der App-Registrierung abwarten</p>
  <h2>Entscheide</h2>
  <table><tr><td><p><b>Thema</b></p></td><td><p><b>Entscheid</b></p></td></tr>
    <tr><td><p>Werkzeug</p></td><td><p>ConfluenceSync im Pilot verwenden</p></td></tr>
    <tr><td><p>Pilotgruppe</p></td><td><p>3 Personen</p></td></tr></table>
</div>
<div style="position:absolute;left:48px;top:620px;width:400px">
  <p>Screenshot vom Entwurf:</p>
  <img src="https://graph.microsoft.com/v1.0/demo/resources/chart/$value" data-src-type="image/png"
       width="320" height="160" alt="Entwurf Dashboard" />
  <object data-attachment="Protokoll.pdf" type="application/pdf" data="https://graph.microsoft.com/x"></object>
</div>
</body></html>""",
    },
    "demo-idee": {
        "title": "Ideen für das Onboarding",
        "section": "section:projekte",
        "edited": datetime(2026, 10, 30, 14, 5, tzinfo=timezone.utc),
        "html": """
<html><head><title>Ideen für das Onboarding</title></head><body>
<h1>Ausgangslage</h1>
<p>Neue Kolleginnen und Kollegen finden die Dokumentation heute an <i>vielen</i> Orten.</p>
<h2>Vorschläge</h2>
<ol><li>Startseite in Confluence mit allen Links</li><li>Kurze Videos zu den wichtigsten Abläufen</li>
<li>Checkliste für die erste Woche</li></ol>
<p data-tag="question">Wer pflegt die Startseite?</p>
</body></html>""",
    },
    "demo-howto": {
        "title": "Anleitung: Bericht exportieren",
        "section": "section:projekte",
        "edited": datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
        "html": """
<html><head><title>Anleitung: Bericht exportieren</title></head><body>
<p>So exportierst du den Monatsbericht:</p>
<ol><li>Bericht öffnen</li><li>Auf <b>Exportieren</b> klicken</li><li>Format <code>PDF</code> wählen</li></ol>
</body></html>""",
    },
}


def demo_png(width: int = 320, height: int = 160) -> bytes:
    """A small bar chart as PNG (no image library needed)."""
    bars = [(30, 0.45), (100, 0.75), (170, 0.55), (240, 0.9)]
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            colour = (246, 248, 252)
            for bx, h in bars:
                if bx <= x < bx + 50 and y >= height - int(h * (height - 20)):
                    colour = (37, 99, 235) if bx != 240 else (234, 88, 12)
            if y == height - 1:
                colour = (148, 163, 184)
            row += bytes(colour)
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


class DemoConnector:
    source = "demo"

    def __init__(self) -> None:
        self.pages = {k: dict(v) for k, v in PAGES.items()}

    def children(self, parent_id: str | None) -> list[SourceNode]:
        if not parent_id:
            return [SourceNode(id="notebook:team", title="Team-Notizen", kind="notebook", has_children=True)]
        if parent_id == "notebook:team":
            return [SourceNode(id="section:besprechungen", title="Besprechungen", kind="section", has_children=True),
                    SourceNode(id="section:projekte", title="Projekte", kind="section", has_children=True)]
        return [SourceNode(id=pid, title=p["title"], kind="page", edited_at=p["edited"])
                for pid, p in self.pages.items() if p["section"] == parent_id]

    def search(self, query: str) -> list[SourceNode]:
        return [SourceNode(id=pid, title=p["title"], kind="page", edited_at=p["edited"])
                for pid, p in self.pages.items() if query.lower() in p["title"].lower()]

    def page_info(self, page_id: str) -> PageInfo | None:
        page = self.pages.get(page_id)
        return PageInfo(title=page["title"], edited_at=page["edited"]) if page else None

    def load(self, page_id: str) -> SourceDocument:
        page = self.pages.get(page_id)
        if not page:
            raise SourceError("Nicht gefunden.")
        _, blocks = parse_onenote_html(page["html"])
        return SourceDocument(source="demo", source_id=page_id, title=page["title"],
                              source_edited_at=page["edited"], blocks=blocks)

    def download_image(self, image: Image) -> bytes:
        return demo_png()


class FakeConfluence:
    """In-memory stand-in for ConfluenceClient (same methods)."""

    def __init__(self) -> None:
        self.base = DEMO_BASE
        self.pages: dict[str, Page] = {}
        self.attachments: dict[str, dict[str, bytes]] = {}
        self._next = 1000
        self.add_page("DOKU", None, "Dokumentation", "<p>Startseite</p>")
        self.add_page("DOKU", "1000", "Besprechungen", "<p>Alle Protokolle</p>")
        self.add_page("DOKU", "1000", "Anleitungen", "<p>Wie mache ich …</p>")
        self.add_page("~demo", None, "Persönlicher Bereich", "<p></p>")

    def add_page(self, space: str, parent_id: str | None, title: str, body: str) -> Page:
        page_id = str(self._next)
        self._next += 1
        page = Page(page_id, title, 1, parent_id, space, norm(body),
                    f"{self.base}/pages/viewpage.action?pageId={page_id}")
        self.pages[page_id] = page
        return page

    def current_user(self) -> dict:
        return {"name": "Demo Nutzerin", "username": "demo"}

    def spaces(self, max_items: int = 1000) -> list[dict]:
        return [{"key": "~demo", "name": "Demo Nutzerin", "personal": True},
                {"key": "DOKU", "name": "Team-Dokumentation", "personal": False}]

    def search_pages(self, space: str, query: str = "", limit: int = 25) -> list[dict]:
        return [{"id": p.id, "title": p.title, "path": self.pages[p.parent_id].title if p.parent_id else ""}
                for p in self.pages.values()
                if p.space_key == space and query.lower() in p.title.lower()][:limit]

    def get_page(self, page_id: str, body: bool = False) -> Page:
        page = self.pages.get(page_id)
        if not page:
            raise ConfluenceError("not found", 404)
        return Page(**{**page.__dict__, "body": page.body if body else None})

    def find_title(self, space: str, title: str) -> list[Page]:
        return [p for p in self.pages.values() if p.space_key == space and p.title == title]

    def create_page(self, space: str, parent_id: str | None, title: str, body: str) -> Page:
        if self.find_title(space, title):
            raise ConfluenceError("A page with this title already exists", 400)
        return self.add_page(space, parent_id, title, body)

    def update_page(self, page: Page, title: str, body: str) -> Page:
        current = self.pages[page.id]
        if current.version != page.version:
            raise ConfluenceError("version conflict", 409)
        current.version += 1
        current.title = title
        current.body = norm(body)
        return self.get_page(page.id)

    def edit_by_hand(self, page_id: str, body: str) -> None:
        page = self.pages[page_id]
        page.version += 1
        page.body = body

    def attachment_names(self, page_id: str) -> set[str]:
        return set(self.attachments.get(page_id, {}))

    def upload_attachment(self, page_id: str, filename: str, data: bytes, mime: str) -> None:
        self.attachments.setdefault(page_id, {})[filename] = data
