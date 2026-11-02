"""Preview of a note as Confluence page, with all publish/update decisions on the right."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QByteArray, Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit, QScrollArea, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..formatter.preview import to_preview_html
from ..model import SOURCE_LABELS, images, unsupported
from ..sync import planner
from ..sync.publisher import Prepared
from .page import Page
from .widgets import (Badge, Card, HelpBox, Note, TargetPicker, button, clear, confirm, field, hbox, label,
                      open_url)
from .worker import run_task

IMAGE_SCHEME = "csimg"


class PreviewBrowser(QTextBrowser):
    """QTextBrowser that shows pre-downloaded images and opens links in the system browser."""

    def __init__(self):
        super().__init__()
        self.images: dict[str, bytes] = {}
        self.setOpenLinks(False)
        self.anchorClicked.connect(lambda url: open_url(url.toString()))

    def loadResource(self, kind: int, url: QUrl):  # noqa: N802 - Qt API
        if kind == QTextDocument.ImageResource and url.scheme() == IMAGE_SCHEME:
            data = self.images.get(url.path())
            image = QImage()
            if data:
                image.loadFromData(QByteArray(data))
            if image.isNull():
                image = QImage(320, 60, QImage.Format_RGB32)
                image.fill(0xEEF0F4)
            return image
        return super().loadResource(kind, url)


def load_preview(services, source: str, source_id: str) -> Prepared:
    """Worker: prepare the page and download its images for the preview."""
    prepared = services.prepare(source, source_id)
    for image in images(prepared.doc):
        try:
            services.image(prepared, image.filename)
        except Exception:  # noqa: BLE001 - a missing image must not block the preview
            pass
    return prepared


class PreviewPage(Page):
    title = "Vorschau"
    subtitle = "So wird die Seite in Confluence aussehen. Erst wenn du bestätigst, wird etwas veröffentlicht."

    def __init__(self, win):
        super().__init__(win, scroll=False, max_width=1500)
        self.prepared: Prepared | None = None
        self.source = ""
        self.source_id = ""
        self.origin = "sources"
        self.back_btn = button("← Zurück", "ghost", lambda: self.win.go(self.origin))
        self.reload_btn = button("↻ Neu laden", None, self.reload)
        self.actions.addWidget(self.back_btn)
        self.actions.addWidget(self.reload_btn)

        row = QHBoxLayout()
        row.setSpacing(20)
        self.body.addLayout(row, 1)
        self.browser = PreviewBrowser()
        self.browser.setMinimumWidth(520)
        row.addWidget(self.browser, 1)

        side_area = QScrollArea()
        side_area.setWidgetResizable(True)
        side_area.setFixedWidth(400)
        side_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_body = QWidget()
        side_body.setObjectName("scrollBody")
        self.side = QVBoxLayout(side_body)
        self.side.setContentsMargins(0, 0, 6, 0)
        self.side.setSpacing(12)
        side_area.setWidget(side_body)
        row.addWidget(side_area)

    # ------------------------------------------------------------------ loading

    def on_show(self, source: str | None = None, source_id: str | None = None, origin: str | None = None,
                **kwargs) -> None:
        if origin:
            self.origin = origin
        self.back_btn.setText("← Meine Veröffentlichungen" if self.origin == "publications" else "← Zurück zu den Notizen")
        if source and source_id:
            self.source, self.source_id = source, source_id
            self.reload()

    def reload(self) -> None:
        if not self.source_id:
            return
        self.prepared = None
        self.title_label.setText("Vorschau")
        self.browser.setHtml("<p style='color:#7a8396; font-family:Segoe UI; font-size:11pt;'>"
                             "Notiz wird geladen und für Confluence aufbereitet …</p>")
        clear(self.side)
        card = Card()
        card.add(label("⏳  Einen Moment …", "h3"))
        card.add(label("Die Notiz wird geladen und mit Confluence verglichen.", "muted"))
        self.side.addWidget(card)
        self.side.addStretch(1)
        self.reload_btn.setEnabled(False)
        key = (self.source, self.source_id)
        run_task(load_preview, self.services, self.source, self.source_id,
                 on_done=lambda p: key == (self.source, self.source_id) and self._show(p),
                 on_error=lambda m: key == (self.source, self.source_id) and self._failed(m))

    def _failed(self, message: str) -> None:
        self.reload_btn.setEnabled(True)
        self.browser.setHtml("")
        clear(self.side)
        card = Card()
        card.add(Note("err", f"<b>Die Vorschau konnte nicht erstellt werden.</b><br>{escape(message)}"))
        card.add(hbox(button("Erneut versuchen", "primary", self.reload),
                      button("Verbindungen prüfen", None, lambda: self.win.go("connections")), None))
        self.side.addWidget(card)
        self.side.addStretch(1)

    def _show(self, prepared: Prepared) -> None:
        self.prepared = prepared
        self.reload_btn.setEnabled(True)
        doc = prepared.doc
        self.title_label.setText(f"Vorschau: {doc.title}")
        self.browser.images = dict(prepared.image_cache)
        self.browser.document().clear()
        self.browser.setHtml(to_preview_html(doc, lambda img: f"{IMAGE_SCHEME}:{img.filename}"))
        self._build_side(prepared)

    # ------------------------------------------------------------------ side panel

    def _build_side(self, p: Prepared) -> None:
        clear(self.side)
        doc = p.doc
        status = "new" if p.action == "create" else p.status
        text = "Neue Seite" if p.action == "create" else planner.STATUS_LABELS.get(p.status, p.status)

        info = Card(spacing=10)
        info.add(hbox(label("Status", "muted", wrap=False), Badge(status, text), None))
        links = []
        if doc.source_url:
            links.append(button(f"In {SOURCE_LABELS.get(doc.source, doc.source)} öffnen ↗", "link",
                                lambda: open_url(doc.source_url)))
        if p.page and p.page.url:
            links.append(button("In Confluence öffnen ↗", "link", lambda: open_url(p.page.url)))
        if links:
            info.add(hbox(*links, None, spacing=16))
        if p.page_missing:
            info.add(Note("warn", "Die früher veröffentlichte Confluence-Seite gibt es nicht mehr (gelöscht oder "
                                  "verschoben). Du kannst die Notiz neu veröffentlichen."))
        if p.problems:
            info.add(Note("err", "<b>Das kann so nicht veröffentlicht werden:</b><br>" +
                          "<br>".join(escape(x) for x in p.problems)))
        missing = unsupported(doc)
        if missing:
            items = "".join(f"<li>{escape(u.note)}</li>" for u in missing[:8])
            info.add(Note("warn", f"<b>{len(missing)} Element(e) können nicht übernommen werden.</b> Sie sind in der "
                                  f"Vorschau markiert und erscheinen in Confluence als Hinweis.<ul>{items}</ul>"))
        self.side.addWidget(info)

        if p.action == "create":
            self._create_card(p)
        else:
            self._update_card(p)
        self.side.addStretch(1)

    def _create_card(self, p: Prepared) -> None:
        card = Card(spacing=10)
        card.add(label("Veröffentlichen", "h3"))
        self.title_edit = QLineEdit(p.title)
        card.add(field("Seitentitel in Confluence", self.title_edit))
        self.target = TargetPicker(self.services)
        card.add(self.target)
        s = self.services.config
        if p.mapping and p.mapping.space:
            self.target.load(p.mapping.space, p.mapping.parent_id or "", "")
        else:
            self.target.load(s.default_space, s.default_parent_id, s.default_parent_title)
        publish = button("🚀  In Confluence veröffentlichen", "primary", lambda: self._publish("publish"))
        publish.setMinimumHeight(42)
        self.publish_buttons = [publish]

        def check() -> None:
            publish.setEnabled(bool(self.title_edit.text().strip() and self.target.value()["space"]
                                    and not p.problems))

        self.title_edit.textChanged.connect(check)
        self.target.changed.connect(check)
        check()
        card.add(publish)
        card.add(label("Neue Seiten werden mit einem Hinweis «Erstellt mit ConfluenceSync» versehen.", "muted"))
        self.side.addWidget(card)

    def _update_card(self, p: Prepared) -> None:
        card = Card(spacing=10)
        self.title_edit = QLineEdit(p.title)
        self.publish_buttons = []
        if p.status == planner.SYNCED:
            card.add(label("Alles aktuell", "h3"))
            card.add(Note("ok", "Die Confluence-Seite zeigt bereits den Stand deiner Notiz."))
            card.add(field("Seitentitel", self.title_edit))
            again = button("Trotzdem neu veröffentlichen", None, lambda: self._publish("publish"))
            self.publish_buttons = [again]
            card.add(again)
        elif p.status == planner.SOURCE_CHANGED:
            card.add(label("Aktualisieren", "h3"))
            card.add(Note("info", "Deine Notiz hat sich seit der letzten Veröffentlichung geändert. "
                                  "In Confluence hat niemand etwas verändert."))
            card.add(field("Seitentitel", self.title_edit))
            update = button("⟳  Confluence-Seite aktualisieren", "primary", lambda: self._publish("publish"))
            update.setMinimumHeight(42)
            self.publish_buttons = [update]
            card.add(update)
        else:
            both = p.status == planner.REVIEW
            card.add(label("Bitte entscheiden", "h3"))
            card.add(Note("warn", "<b>Die Seite wurde direkt in Confluence bearbeitet</b>" +
                          (" – und deine Notiz hat sich auch geändert." if both else ".") +
                          " ConfluenceSync überschreibt nichts ohne deine Zustimmung."))
            card.add(label("<b>Confluence-Version behalten:</b> Die Seite bleibt wie sie ist. Die Änderungen "
                           "gelten als übernommen.<br><b>Mit Quelle überschreiben:</b> Die Seite wird durch deine "
                           "Notiz ersetzt. Änderungen in Confluence gehen verloren (bleiben aber im "
                           "Seitenverlauf von Confluence erhalten).", "muted", rich=True))
            keep = button("Confluence-Version behalten", None, lambda: self._publish("keep_confluence"))
            overwrite = button("Mit Quelle überschreiben", "danger", self._overwrite)
            cancel = button("Abbrechen", "ghost", lambda: self.win.go(self.origin))
            for b in (keep, overwrite):
                b.setMinimumHeight(38)
                card.add(b)
            card.add(cancel)
            self.publish_buttons = [overwrite]
        if p.lost:
            items = "".join(f"<li>{escape(x)}</li>" for x in p.lost[:8])
            card.add(Note("warn", f"<b>Achtung:</b> Diese Elemente gibt es nur in Confluence und sie würden beim "
                                  f"Aktualisieren entfernt:<ul>{items}</ul>"))
            self.lost_ok = QCheckBox("Ich habe das gelesen und möchte trotzdem aktualisieren.")
            card.add(self.lost_ok)
            for b in self.publish_buttons:
                b.setEnabled(False)
                self.lost_ok.toggled.connect(b.setEnabled)
        if p.problems:
            for b in self.publish_buttons:
                b.setEnabled(False)
        self.side.addWidget(card)
        if p.diff:
            self.side.addWidget(HelpBox("Was sich in Confluence ändert", diff_html(p.diff)))

    # ------------------------------------------------------------------ actions

    def _overwrite(self) -> None:
        if confirm(self, "Mit Quelle überschreiben?",
                   "Die Änderungen, die direkt in Confluence gemacht wurden, werden durch deine Notiz ersetzt.\n\n"
                   "Frühere Versionen bleiben im Seitenverlauf von Confluence erhalten.",
                   "Überschreiben", danger=True):
            self._publish("overwrite")

    def _publish(self, decision: str) -> None:
        p = self.prepared
        if p is None:
            return
        target = self.target.value() if p.action == "create" else {}
        for b in self.publish_buttons:
            b.setEnabled(False)
            b.setText("Wird veröffentlicht …")
        self.reload_btn.setEnabled(False)
        run_task(self.services.publish, p, decision, self.title_edit.text().strip(),
                 target.get("space", ""), target.get("space_name", ""), target.get("parent_id", ""),
                 target.get("parent_title", ""),
                 on_done=lambda m: self._published(m, decision), on_error=self._publish_failed)

    def _publish_failed(self, message: str) -> None:
        self.reload_btn.setEnabled(True)
        if self.prepared:
            self._build_side(self.prepared)
        self.side.insertWidget(0, Note("err", f"<b>Nicht veröffentlicht.</b><br>{escape(message)}"))

    def _published(self, mapping, decision: str) -> None:
        self.reload_btn.setEnabled(True)
        self.win.refresh_status()
        clear(self.side)
        card = Card(spacing=12)
        if decision == "keep_confluence":
            card.add(label("✅  Confluence-Version behalten", "h2"))
            card.add(label("Die Seite bleibt unverändert. Sie gilt jetzt wieder als aktuell.", "muted"))
        else:
            card.add(label("🎉  Veröffentlicht!", "h2"))
            card.add(label(f"«{escape(mapping.title or '')}» ist jetzt in Confluence.", "muted", rich=True))
        if mapping.confluence_url:
            card.add(button("In Confluence öffnen ↗", "primary", lambda: open_url(mapping.confluence_url)))
        card.add(button("Zu meinen Veröffentlichungen", None, lambda: self.win.go("publications")))
        card.add(button("Weitere Notiz wählen", "ghost", lambda: self.win.go("sources")))
        self.side.addWidget(card)
        self.side.addStretch(1)
        self.prepared = None


def diff_html(diff: list[dict]) -> str:
    rows = []
    for entry in diff[:120]:
        colour, sign = ("#15803d", "+") if entry["op"] == "+" else ("#c62828", "−")
        rows.append(f"<div style='color:{colour}'>{sign} {escape(entry['text'][:300])}</div>")
    if len(diff) > 120:
        rows.append("<div>…</div>")
    return ("<div style='font-family:Consolas; font-size:9pt;'>" + "".join(rows) + "</div>"
            "<p style='color:#7a8396'>Grün = kommt dazu, Rot = fällt weg.</p>")
