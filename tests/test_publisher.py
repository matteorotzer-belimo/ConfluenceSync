from __future__ import annotations

from datetime import datetime, timezone

import pytest

from confluencesync.confluence.client import ConfluenceError
from confluencesync.demo import demo_png
from confluencesync.model import images
from confluencesync.sync import planner
from confluencesync.sync.publisher import PublishError, image_bytes, prepare, publish, refresh_status, text_blocks, text_diff

PAGE_ID = "demo-besprechung"
TITLE = "Teamsitzung 28. Oktober"


class CountingConfluence:
    """Wraps FakeConfluence and records uploads."""

    def __init__(self, fake):
        self.fake = fake
        self.uploads: list[tuple[str, str]] = []

    def __getattr__(self, name):
        return getattr(self.fake, name)

    def upload_attachment(self, page_id, filename, data, mime):
        self.uploads.append((page_id, filename))
        self.fake.upload_attachment(page_id, filename, data, mime)


@pytest.fixture
def confluence(fake):
    return CountingConfluence(fake)


def create(store, confluence, demo, source_id=PAGE_ID, **kwargs):
    prepared = prepare(store, confluence, demo, source_id)
    args = {"space": "DOKU", "parent_id": "1001", **kwargs}
    return publish(store, confluence, demo, prepared, "publish", **args)


def edit_source(demo, source_id=PAGE_ID, text="Neuer Punkt aus der Quelle."):
    page = demo.pages[source_id]
    page["html"] = page["html"].replace("</body>", f"<p>{text}</p></body>")
    page["edited"] = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def edit_confluence(fake, mapping, extra="<p>Von Hand ergänzt.</p>"):
    page = fake.pages[mapping.confluence_page_id]
    fake.edit_by_hand(page.id, page.body + extra)


# --------------------------------------------------------------------------- create


def test_prepare_new_page(store, confluence, demo):
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.action == "create"
    assert prepared.mapping is None and prepared.page is None
    assert prepared.title == TITLE
    assert prepared.problems == []
    assert "Erstellt mit ConfluenceSync" in prepared.storage


def test_prepare_unknown_source_page(store, confluence, demo):
    with pytest.raises(PublishError, match="Nicht gefunden"):
        prepare(store, confluence, demo, "does-not-exist")


def test_create_page(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    page = fake.pages[mapping.confluence_page_id]
    assert page.title == TITLE and page.space_key == "DOKU" and page.parent_id == "1001"
    assert "Stand der Auswertungen" in page.body
    assert mapping.id is not None
    assert mapping.status == planner.SYNCED
    assert mapping.published_version == 1
    assert mapping.space == "DOKU" and mapping.parent_id == "1001"
    assert mapping.confluence_url.endswith(f"pageId={page.id}")
    assert store.by_source("demo", PAGE_ID) == mapping
    runs = store.runs()
    assert [(r.action, r.result) for r in runs] == [("create", "ok")]
    assert runs[0].title == TITLE and runs[0].mapping_id == mapping.id


def test_create_uploads_images_as_attachments(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    doc_images = images(demo.load(PAGE_ID))
    assert len(doc_images) == 1
    filename = doc_images[0].filename
    assert confluence.uploads == [(mapping.confluence_page_id, filename)]
    assert fake.attachments[mapping.confluence_page_id][filename] == demo_png()
    assert f'ri:filename="{filename}"' in fake.pages[mapping.confluence_page_id].body


def test_duplicate_title_is_refused(store, confluence, demo, fake):
    create(store, confluence, demo)
    prepared = prepare(store, confluence, demo, "demo-idee")
    pages_before = len(fake.pages)
    with pytest.raises(PublishError, match="gibt es schon eine Seite"):
        publish(store, confluence, demo, prepared, "publish", title=TITLE, space="DOKU")
    assert len(fake.pages) == pages_before
    assert store.by_source("demo", "demo-idee") is None
    last = store.runs()[0]
    assert (last.action, last.result, last.source_id) == ("create", "error", "demo-idee")


def test_create_requires_space_and_title(store, confluence, demo):
    prepared = prepare(store, confluence, demo, PAGE_ID)
    with pytest.raises(PublishError, match="Space"):
        publish(store, confluence, demo, prepared, "publish", space="")
    prepared.title = "   "
    with pytest.raises(PublishError, match="Titel"):
        publish(store, confluence, demo, prepared, "publish", space="DOKU")


def test_publish_refused_when_storage_has_problems(store, confluence, demo, fake):
    prepared = prepare(store, confluence, demo, PAGE_ID)
    prepared.problems = ["Makro «jira» ist nicht erlaubt."]
    with pytest.raises(PublishError, match="kann nicht veröffentlicht werden"):
        publish(store, confluence, demo, prepared, "publish", space="DOKU")
    assert not any(p.title == TITLE for p in fake.pages.values())


def test_keep_confluence_without_existing_page_is_refused(store, confluence, demo):
    prepared = prepare(store, confluence, demo, PAGE_ID)
    with pytest.raises(PublishError, match="keine Confluence-Seite"):
        publish(store, confluence, demo, prepared, "keep_confluence", space="DOKU")


# --------------------------------------------------------------------------- update


def test_unchanged_page_is_synced(store, confluence, demo):
    create(store, confluence, demo)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.action == "update"
    assert prepared.status == planner.SYNCED
    assert not prepared.source_changed and not prepared.confluence_changed
    assert prepared.diff == [] and prepared.lost == []


def test_update_when_source_changed(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_source(demo)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.status == planner.SOURCE_CHANGED
    assert {"op": "+", "text": "Neuer Punkt aus der Quelle."} in prepared.diff
    updated = publish(store, confluence, demo, prepared, "publish")
    page = fake.pages[mapping.confluence_page_id]
    assert page.version == 2 and "Neuer Punkt aus der Quelle." in page.body
    assert updated.id == mapping.id and updated.published_version == 2
    assert updated.status == planner.SYNCED
    assert updated.source_edited_at == "2026-11-01T12:00:00+00:00"
    assert len(confluence.uploads) == 1           # image already attached, not uploaded again
    assert [r.action for r in store.runs()] == ["update", "create"]
    assert prepare(store, confluence, demo, PAGE_ID).status == planner.SYNCED


def test_update_keeps_renamed_title(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_source(demo)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    publish(store, confluence, demo, prepared, "publish", title="Neuer Titel")
    assert fake.pages[mapping.confluence_page_id].title == "Neuer Titel"
    assert store.get(mapping.id).title == "Neuer Titel"
    assert prepare(store, confluence, demo, PAGE_ID).title == "Neuer Titel"


def test_manual_confluence_edit_requires_decision(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.status == planner.CONFLUENCE_CHANGED
    assert prepared.confluence_changed and not prepared.source_changed
    assert {"op": "-", "text": "Von Hand ergänzt."} in prepared.diff
    with pytest.raises(PublishError, match="von Hand geändert"):
        publish(store, confluence, demo, prepared, "publish")
    page = fake.pages[mapping.confluence_page_id]
    assert "Von Hand ergänzt." in page.body and page.version == 2
    stored = store.get(mapping.id)
    assert "von Hand geändert" in stored.last_error
    assert (store.runs()[0].action, store.runs()[0].result) == ("update", "error")


def test_overwrite_replaces_manual_edit(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    result = publish(store, confluence, demo, prepared, "overwrite")
    page = fake.pages[mapping.confluence_page_id]
    assert "Von Hand ergänzt." not in page.body
    assert page.version == 3 and result.published_version == 3
    assert result.status == planner.SYNCED and result.last_error is None
    assert prepare(store, confluence, demo, PAGE_ID).status == planner.SYNCED


def test_keep_confluence_marks_synced_without_changing_page(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    body_before = fake.pages[mapping.confluence_page_id].body
    result = publish(store, confluence, demo, prepared, "keep_confluence")
    page = fake.pages[mapping.confluence_page_id]
    assert page.body == body_before and page.version == 2
    assert result.status == planner.SYNCED and result.published_version == 2
    assert store.runs()[0].action == "keep"
    assert prepare(store, confluence, demo, PAGE_ID).status == planner.SYNCED
    assert refresh_status(store, confluence, demo, store.get(mapping.id)).status == planner.SYNCED


def test_review_when_both_sides_changed(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping)
    edit_source(demo)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.status == planner.REVIEW
    with pytest.raises(PublishError):
        publish(store, confluence, demo, prepared, "publish")
    publish(store, confluence, demo, prepared, "overwrite")
    assert "Neuer Punkt aus der Quelle." in fake.pages[mapping.confluence_page_id].body


def test_concurrent_edit_after_preview_is_refused(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_source(demo)
    prepared = prepare(store, confluence, demo, PAGE_ID)
    edit_confluence(fake, mapping)
    with pytest.raises(PublishError, match="seit der Vorschau"):
        publish(store, confluence, demo, prepared, "overwrite")
    assert "Von Hand ergänzt." in fake.pages[mapping.confluence_page_id].body


def test_lost_items_are_reported_in_preview(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping, '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">X-1'
                                   "</ac:parameter></ac:structured-macro>")
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.lost == ["App-Makro «jira»"]


def test_deleted_page_can_be_published_again(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    del fake.pages[mapping.confluence_page_id]
    assert refresh_status(store, confluence, demo, mapping).status == planner.PAGE_MISSING
    prepared = prepare(store, confluence, demo, PAGE_ID)
    assert prepared.page_missing and prepared.status == planner.PAGE_MISSING
    assert prepared.action == "create"
    result = publish(store, confluence, demo, prepared, "publish", space="DOKU")
    assert result.id == mapping.id
    assert result.confluence_page_id != mapping.confluence_page_id
    assert result.confluence_page_id in fake.pages
    assert len(store.mappings()) == 1
    assert result.status == planner.SYNCED


def test_confluence_error_is_mapped_to_publish_error(store, confluence, demo, fake, monkeypatch):
    create(store, confluence, demo)

    def forbidden(*_args, **_kwargs):
        raise ConfluenceError("GET /content -> HTTP 403", 403)

    monkeypatch.setattr(fake, "get_page", forbidden)
    with pytest.raises(PublishError, match="Berechtigung"):
        prepare(store, confluence, demo, PAGE_ID)


def test_image_bytes_cache_and_unknown_image(store, confluence, demo, monkeypatch):
    prepared = prepare(store, confluence, demo, PAGE_ID)
    filename = images(prepared.doc)[0].filename
    calls = []
    original = demo.download_image
    monkeypatch.setattr(demo, "download_image", lambda image: calls.append(image) or original(image))
    assert image_bytes(prepared, demo, filename) == demo_png()
    assert image_bytes(prepared, demo, filename) == demo_png()
    assert len(calls) == 1
    with pytest.raises(PublishError, match="Bild nicht gefunden"):
        image_bytes(prepared, demo, "cs-unknown.png")


# --------------------------------------------------------------------------- status check


def test_refresh_status_synced(store, confluence, demo):
    mapping = create(store, confluence, demo)
    result = refresh_status(store, confluence, demo, mapping)
    assert result.status == planner.SYNCED and result.last_error is None
    assert result.last_checked_at


def test_refresh_status_source_changed(store, confluence, demo):
    mapping = create(store, confluence, demo)
    edit_source(demo)
    assert refresh_status(store, confluence, demo, mapping).status == planner.SOURCE_CHANGED
    assert store.get(mapping.id).status == planner.SOURCE_CHANGED


def test_refresh_status_new_timestamp_but_same_content(store, confluence, demo):
    mapping = create(store, confluence, demo)
    demo.pages[PAGE_ID]["edited"] = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    result = refresh_status(store, confluence, demo, mapping)
    assert result.status == planner.SYNCED
    assert result.source_edited_at == "2026-11-02T08:00:00+00:00"


def test_refresh_status_confluence_changed_and_review(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    edit_confluence(fake, mapping)
    assert refresh_status(store, confluence, demo, mapping).status == planner.CONFLUENCE_CHANGED
    edit_source(demo)
    assert refresh_status(store, confluence, demo, mapping).status == planner.REVIEW


def test_refresh_status_title_only_change_is_not_a_manual_edit(store, confluence, demo, fake):
    mapping = create(store, confluence, demo)
    page = fake.pages[mapping.confluence_page_id]
    page.version += 1
    page.title = "Umbenannt"
    result = refresh_status(store, confluence, demo, mapping)
    assert result.status == planner.SYNCED
    assert result.published_version == 2 and result.title == "Umbenannt"


def test_refresh_status_missing_source_and_unknown_connector(store, confluence, demo):
    mapping = create(store, confluence, demo)
    assert refresh_status(store, confluence, None, mapping).status == planner.UNKNOWN
    assert store.get(mapping.id).last_error == "Quelle ist nicht verbunden."
    del demo.pages[PAGE_ID]
    assert refresh_status(store, confluence, demo, mapping).status == planner.SOURCE_MISSING


def test_refresh_status_error(store, confluence, demo, fake, monkeypatch):
    mapping = create(store, confluence, demo)

    def unauthorized(*_args, **_kwargs):
        raise ConfluenceError("HTTP 401", 401)

    monkeypatch.setattr(fake, "get_page", unauthorized)
    result = refresh_status(store, confluence, demo, mapping)
    assert result.status == planner.ERROR
    assert "Zugriffstoken" in result.last_error


# --------------------------------------------------------------------------- diff helpers


def test_text_blocks_and_diff():
    storage = ('<h2>Titel</h2><ul><li>a</li><li>b</li></ul>'
               '<table><tbody><tr><td>x</td><td>y</td></tr></tbody></table>'
               '<ac:task-list><ac:task><ac:task-id>1</ac:task-id><ac:task-status>complete</ac:task-status>'
               '<ac:task-body>fertig</ac:task-body></ac:task></ac:task-list>'
               '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Hinweis</p></ac:rich-text-body>'
               '</ac:structured-macro><p><ac:image><ri:attachment ri:filename="cs-x.png" /></ac:image></p>')
    assert text_blocks(storage) == ["Titel", "• a", "• b", "x | y", "☑ fertig", "[info]", "Hinweis", "[Bild]"]
    assert text_blocks("<p>kaputt") == ["<p>kaputt"]
    assert text_diff("<p>a</p><p>b</p>", "<p>a</p><p>c</p>") == [{"op": "-", "text": "b"}, {"op": "+", "text": "c"}]
