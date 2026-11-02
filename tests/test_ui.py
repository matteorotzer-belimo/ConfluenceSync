"""pytest-qt smoke test: drive the main window through the demo publish flow (no network, inline tasks)."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from confluencesync.demo import DEMO_BASE
from confluencesync.services import Services
from confluencesync.sync import planner
from confluencesync.ui import preview_page, worker
from confluencesync.ui.logo import app_icon
from confluencesync.ui.main_window import MainWindow
from confluencesync.ui.style import QSS


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "SYNC", True)
    app = QApplication.instance()
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    services = Services(tmp_path / "data", demo=True)
    window = MainWindow(services, check_updates=False)
    qtbot.addWidget(window)
    window.resize(1280, 820)
    window.show()
    yield window
    window.close()
    services.store.close()
    app.setStyleSheet("")


def texts(widget, cls) -> list[str]:
    return [w.text() for w in widget.findChildren(cls)]


def side_button(preview, text: str) -> QPushButton:
    matches = [b for b in preview.findChildren(QPushButton) if b.text() == text]
    assert len(matches) == 1, f"button {text!r} not found once in {texts(preview, QPushButton)}"
    return matches[0]


def test_navigation_to_every_page(win):
    assert win.current == "tutorial"
    assert win.stack.currentWidget() is win.pages["tutorial"]
    for name in ("sources", "connections", "settings", "publications", "tutorial"):
        win.go(name)
        assert win.current == name
        assert win.stack.currentWidget() is win.pages[name]
        if name in win.nav_buttons:
            assert win.nav_buttons[name].isChecked()

    # without a Confluence connection the preview shows a friendly error with a retry button
    win.go("preview", source="demo", source_id="demo-besprechung", origin="sources")
    preview = win.pages["preview"]
    assert win.stack.currentWidget() is preview
    assert win.nav_buttons["sources"].isChecked()
    assert preview.prepared is None
    assert any("Confluence ist noch nicht verbunden" in t for t in texts(preview, QLabel))
    retry = side_button(preview, "Erneut versuchen")

    win.services.connect_confluence("https://confluence.example.com", "demo-token-123456")
    retry.click()
    assert preview.prepared is not None and preview.prepared.action == "create"
    assert preview.title_label.text() == "Vorschau: Teamsitzung 28. Oktober"
    html = preview.browser.toHtml()
    assert "Teamsitzung 28. Oktober" in html
    assert preview.back_btn.text() == "← Zurück zu den Notizen"


def test_sources_page_lists_demo_notes(win):
    win.go("sources")
    tree = win.pages["sources"].tree
    assert tree.topLevelItemCount() >= 1
    notebook = tree.invisibleRootItem().child(0)
    notebook.setExpanded(True)
    titles = []

    def walk(item):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setExpanded(True)
            titles.append(child.text(0))
            walk(child)

    walk(notebook)
    assert any("Teamsitzung 28. Oktober" in t for t in titles)


def test_demo_publish_flow_with_conflict(win, monkeypatch):
    services = win.services
    tutorial = win.pages["tutorial"]

    tutorial.show_step(1)
    form = tutorial.confluence_form
    form.url.setText("https://confluence.example.com/")
    form.token.edit.setText("demo-token-123456")
    form.connect_btn.click()
    assert services.status().confluence_connected
    assert "demo-token-123456" not in (services.data_dir / "demo-settings.json").read_text(encoding="utf-8")

    tutorial.show_step(2)
    assert tutorial.target.isVisibleTo(tutorial)
    tutorial.target.space.setCurrentIndex(tutorial.target.space.findData("DOKU"))
    tutorial.target.set_parent("1001", "Besprechungen")
    tutorial.show_step(3)
    assert services.config.default_space == "DOKU"
    assert services.config.default_parent_id == "1001"
    tutorial.show_step(4)
    tutorial._next()
    assert services.config.tutorial_completed
    assert win.current == "sources"

    # publish a new page from the preview
    preview = win.pages["preview"]
    win.go("preview", source="demo", source_id="demo-besprechung", origin="sources")
    assert preview.prepared.action == "create"
    assert preview.title_edit.text() == "Teamsitzung 28. Oktober"
    assert preview.target.value()["space"] == "DOKU"
    assert preview.target.value()["parent_id"] == "1001"
    assert preview.publish_buttons[0].isEnabled()
    preview._publish("publish")
    assert "🎉  Veröffentlicht!" in texts(preview, QLabel)
    assert preview.prepared is None

    pubs = services.publications()
    assert len(pubs) == 1
    mapping = pubs[0]
    assert mapping.status == planner.SYNCED
    assert mapping.space == "DOKU"
    page = services.fake.pages[mapping.confluence_page_id]
    assert page.parent_id == "1001"
    assert mapping.confluence_url.startswith(DEMO_BASE)

    # publications page lists it
    win.go("publications")
    publications = win.pages["publications"]
    assert publications.summary.text().startswith("1 veröffentlichte Seite(n) · alles aktuell")
    assert "Teamsitzung 28. Oktober" in texts(publications.list_area, QLabel)

    # someone edits the page in Confluence → conflict
    services.demo_edit_confluence(mapping.id)
    publications.check()
    assert services.publications()[0].status == planner.CONFLUENCE_CHANGED
    assert "1 brauchen deine Aufmerksamkeit" in publications.summary.text()
    assert "Prüfen und entscheiden …" in texts(publications.list_area, QPushButton)

    win.go("preview", source=mapping.source, source_id=mapping.source_id, origin="publications")
    assert preview.prepared.status == planner.CONFLUENCE_CHANGED
    assert preview.back_btn.text() == "← Meine Veröffentlichungen"
    keep = side_button(preview, "Confluence-Version behalten")
    side_button(preview, "Mit Quelle überschreiben")
    side_button(preview, "Abbrechen")
    version_before = services.fake.pages[mapping.confluence_page_id].version
    body_before = services.fake.pages[mapping.confluence_page_id].body

    keep.click()
    assert "✅  Confluence-Version behalten" in texts(preview, QLabel)
    kept = services.publications()[0]
    assert kept.status == planner.SYNCED
    assert services.fake.pages[mapping.confluence_page_id].version == version_before
    assert services.fake.pages[mapping.confluence_page_id].body == body_before

    # second manual edit, this time overwrite with the source (confirmation dialog mocked)
    services.demo_edit_confluence(mapping.id)
    win.go("publications")
    publications.check()
    win.go("preview", source=mapping.source, source_id=mapping.source_id, origin="publications")
    asked = []
    monkeypatch.setattr(preview_page, "confirm", lambda *a, **kw: asked.append(a[1]) or True)
    side_button(preview, "Mit Quelle überschreiben").click()
    assert asked == ["Mit Quelle überschreiben?"]
    assert "🎉  Veröffentlicht!" in texts(preview, QLabel)
    assert services.fake.pages[mapping.confluence_page_id].version == version_before + 2
    assert services.publications()[0].status == planner.SYNCED

    # history tab shows the runs
    win.go("publications")
    publications.tabs.setCurrentIndex(1)
    assert publications.history.rowCount() == len(services.history()) >= 3
