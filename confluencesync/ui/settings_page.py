"""«Einstellungen»: default target, tutorial, updates, data folder."""
from __future__ import annotations

import os
from html import escape

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox

from .. import __version__
from .page import Page
from .widgets import Card, Note, TargetPicker, button, hbox, label, open_url
from .worker import run_task


def open_folder(path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class SettingsPage(Page):
    title = "Einstellungen"
    subtitle = ""

    def __init__(self, win):
        super().__init__(win, max_width=900)
        s = self.services

        target = Card()
        target.add(label("Standard-Ziel in Confluence", "h2"))
        target.add(label("Wird bei neuen Veröffentlichungen vorausgewählt. Du kannst es jedes Mal ändern.", "muted"))
        self.target_note = Note("warn", "Bitte zuerst Confluence verbinden.")
        target.add(self.target_note)
        self.target = TargetPicker(s)
        target.add(self.target)
        self.target_saved = label("", "muted")
        self.save_btn = button("Speichern", "primary", self._save_target)
        target.add(hbox(self.save_btn, self.target_saved, None))
        self.body.addWidget(target)

        guide = Card()
        guide.add(label("Anleitung", "h2"))
        guide.add(label("Die Schritt-für-Schritt-Anleitung kannst du jederzeit erneut durchgehen.", "muted"))
        guide.add(hbox(button("Anleitung erneut starten", None, lambda: self.win.go("tutorial", step=0)), None))
        self.body.addWidget(guide)

        updates = Card()
        updates.add(label("Updates", "h2"))
        self.update_box = QCheckBox("Beim Start nach neuen Versionen suchen (fragt nur GitHub nach der Versionsnummer)")
        self.update_box.toggled.connect(lambda on: s.update_settings(check_updates=on))
        updates.add(self.update_box)
        self.update_result = label("", "muted", rich=True)
        self.update_result.setOpenExternalLinks(True)
        updates.add(hbox(button("Jetzt prüfen", None, self._check_update), self.update_result, None))
        self.body.addWidget(updates)

        data = Card()
        data.add(label("Daten und Datenschutz", "h2"))
        data.add(label(
            "ConfluenceSync läuft nur auf diesem Laptop. Es gibt keinen Server und keine Cloud dazwischen.<br>"
            "• <b>Zugangsdaten</b> (Confluence-Token, Notion-Token) liegen im Windows-Anmeldeinformationsspeicher.<br>"
            "• <b>Microsoft-Anmeldung</b> wird verschlüsselt (Windows DPAPI) im Datenordner gespeichert.<br>"
            "• <b>Zuordnungen und Verlauf</b> liegen in einer kleinen Datenbank im Datenordner.<br>"
            "• Die <b>Protokolldatei</b> enthält keine Tokens.", "muted", rich=True))
        data.add(label(f"Datenordner: {escape(str(s.data_dir))}", "muted"))
        data.add(hbox(button("Datenordner öffnen", None, lambda: open_folder(s.data_dir)),
                      button("Protokoll öffnen", None, self._open_log), None))
        self.body.addWidget(data)

        about = Card()
        about.add(label("Über ConfluenceSync", "h2"))
        about.add(label(f"Version {__version__}" + (" · Demo-Modus" if s.demo else ""), "muted"))
        about.add(hbox(button("Projekt auf GitHub", "link", lambda: open_url(self.win.repo_url)), None))
        self.body.addWidget(about)
        self.body.addStretch(1)

    def on_show(self, **kwargs) -> None:
        s = self.services.config
        connected = self.services.status(check_onenote=False).confluence_connected
        self.target_note.setVisible(not connected)
        self.target.setVisible(connected)
        self.save_btn.setVisible(connected)
        self.target_saved.setText("")
        if connected:
            self.target.load(s.default_space, s.default_parent_id, s.default_parent_title)
        self.update_box.blockSignals(True)
        self.update_box.setChecked(s.check_updates)
        self.update_box.blockSignals(False)

    def _save_target(self) -> None:
        v = self.target.value()
        self.services.update_settings(default_space=v["space"], default_space_name=v["space_name"],
                                      default_parent_id=v["parent_id"], default_parent_title=v["parent_title"])
        self.target_saved.setText("✓ Gespeichert")

    def _check_update(self) -> None:
        self.update_result.setText("Wird geprüft …")

        def done(release) -> None:
            if release:
                self.update_result.setText(f"Neue Version {escape(release['version'])} verfügbar – "
                                           f"<a href='{escape(release['url'])}'>herunterladen</a>")
            else:
                self.update_result.setText("Du hast die neuste Version (oder GitHub ist nicht erreichbar).")

        run_task(self.services.check_update, on_done=done,
                 on_error=lambda m: self.update_result.setText(escape(m)))

    def _open_log(self) -> None:
        log = self.services.data_dir / "logs" / "confluencesync.log"
        if log.exists():
            os.startfile(str(log))  # noqa: S606 - opens the log in the default text editor
        else:
            open_folder(self.services.data_dir)
