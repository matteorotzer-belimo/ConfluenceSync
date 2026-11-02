"""Preview and publish: source page -> Confluence page, with protection against overwriting."""
from __future__ import annotations

import difflib
import re
import secrets
import time
from dataclasses import dataclass, field

from ..confluence.checks import (check_generated, content_hash, lost_items, parse_storage, q,
                                 StorageError)
from ..confluence.client import ConfluenceError, Page, friendly_message
from ..connectors.base import SourceError
from ..formatter.storage import to_storage
from ..model import SourceDocument, images
from ..store import Mapping, Store, now
from . import planner


class PublishError(Exception):
    """Message for the user (German)."""


@dataclass
class Prepared:
    id: str
    doc: SourceDocument
    storage: str
    action: str                              # create | update
    mapping: Mapping | None = None
    page: Page | None = None                 # current Confluence page (update)
    title: str = ""
    source_changed: bool = True
    confluence_changed: bool = False
    page_missing: bool = False
    status: str = planner.SYNCED
    lost: list[str] = field(default_factory=list)
    diff: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    image_cache: dict[str, bytes] = field(default_factory=dict)
    created: float = field(default_factory=time.time)


# --------------------------------------------------------------------------- text diff


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def text_blocks(storage: str) -> list[str]:
    """Readable lines of a page: one per paragraph, heading, list item, table row, ..."""
    try:
        root = parse_storage(storage)
    except StorageError:
        return [storage]
    lines: list[str] = []

    def visit(el) -> None:
        for child in el:
            tag = child.tag
            if tag in ("ul", "ol"):
                for li in child:
                    lines.append("• " + _text(li))
            elif tag == "table":
                for tr in child.iter("tr"):
                    lines.append(" | ".join(_text(c) for c in tr))
            elif tag == q("ac:structured-macro"):
                name = child.get(q("ac:name"), "")
                body = child.find(q("ac:rich-text-body"))
                if body is not None:
                    lines.append(f"[{name}]")
                    visit(body)
                else:
                    text = _text(child)
                    lines.append(f"[{name}] {text}".strip())
            elif tag == q("ac:task-list"):
                for task in child:
                    status = task.find(q("ac:task-status"))
                    body = task.find(q("ac:task-body"))
                    done = status is not None and (status.text or "") == "complete"
                    lines.append(("☑ " if done else "☐ ") + (_text(body) if body is not None else ""))
            elif tag == q("ac:image") or child.find(".//" + q("ac:image")) is not None:
                lines.append("[Bild]")
            else:
                text = _text(child)
                if text:
                    lines.append(text)

    visit(root)
    return lines


def text_diff(old: str, new: str, limit: int = 200) -> list[dict]:
    out = []
    for line in difflib.unified_diff(text_blocks(old), text_blocks(new), lineterm="", n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        out.append({"op": line[0], "text": line[1:]})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- preview


def prepare(store: Store, confluence, connector, source_id: str) -> Prepared:
    """Load the source page, render it and work out what publishing would do."""
    try:
        doc = connector.load(source_id)
    except SourceError as exc:
        raise PublishError(str(exc)) from None
    storage = to_storage(doc)
    prepared = Prepared(id=secrets.token_urlsafe(12), doc=doc, storage=storage, action="create",
                        title=doc.title, problems=check_generated(storage))
    mapping = store.by_source(doc.source, doc.source_id)
    prepared.mapping = mapping
    if mapping is None:
        return prepared
    prepared.title = mapping.title or doc.title
    try:
        page = confluence.get_page(mapping.confluence_page_id, body=True)
    except ConfluenceError as exc:
        if exc.status == 404:
            prepared.page_missing = True
            prepared.status = planner.PAGE_MISSING
            return prepared
        raise PublishError(friendly_message(exc)) from None
    prepared.action = "update"
    prepared.page = page
    prepared.title = page.title
    prepared.source_changed = doc.content_hash() != mapping.source_hash
    prepared.confluence_changed = planner.confluence_changed(mapping, page)
    prepared.status = planner.decide(prepared.source_changed, prepared.confluence_changed)
    prepared.lost = lost_items(page.body or "", storage)
    prepared.diff = text_diff(page.body or "", storage)
    return prepared


def image_bytes(prepared: Prepared, connector, filename: str) -> bytes:
    if filename not in prepared.image_cache:
        image = next((i for i in images(prepared.doc) if i.filename == filename), None)
        if image is None:
            raise PublishError("Bild nicht gefunden.")
        try:
            prepared.image_cache[filename] = connector.download_image(image)
        except SourceError as exc:
            raise PublishError(str(exc)) from None
    return prepared.image_cache[filename]


# --------------------------------------------------------------------------- publish


def _upload_images(prepared: Prepared, confluence, connector, page_id: str) -> int:
    existing = confluence.attachment_names(page_id)
    count = 0
    for image in images(prepared.doc):
        if image.filename in existing:
            continue
        data = image_bytes(prepared, connector, image.filename)
        confluence.upload_attachment(page_id, image.filename, data, image.mime)
        count += 1
    return count


def _remember(store: Store, prepared: Prepared, page: Page, space: str | None, parent_id: str | None,
              title: str) -> Mapping:
    doc = prepared.doc
    base = prepared.mapping or Mapping(source=doc.source, source_id=doc.source_id, confluence_page_id=page.id)
    mapping = base.model_copy(update={
        "source_title": doc.title, "source_url": doc.source_url,
        "source_edited_at": doc.source_edited_at.isoformat() if doc.source_edited_at else None,
        "source_hash": doc.content_hash(), "confluence_page_id": page.id, "confluence_url": page.url,
        "space": space or page.space_key, "parent_id": parent_id or page.parent_id, "title": title,
        "published_version": page.version, "published_hash": content_hash(page.body or ""),
        "status": planner.SYNCED, "last_run_at": now(), "last_checked_at": now(), "last_error": None})
    return store.save(mapping)


def publish(store: Store, confluence, connector, prepared: Prepared, decision: str, title: str = "",
            space: str = "", parent_id: str = "") -> Mapping:
    """decision: 'publish' (normal), 'overwrite' (despite manual changes) or 'keep_confluence'."""
    title = (title or prepared.title).strip()
    if prepared.problems:
        raise PublishError("Die Seite kann nicht veröffentlicht werden: " + " ".join(prepared.problems))
    if not title:
        raise PublishError("Bitte einen Titel eingeben.")
    try:
        if decision == "keep_confluence":
            return _keep_confluence(store, prepared)
        if prepared.action == "update":
            mapping = _update(store, confluence, connector, prepared, decision, title)
            store.add_run("update", "ok", "Seite aktualisiert", mapping)
        else:
            mapping = _create(store, confluence, connector, prepared, title, space, parent_id)
            store.add_run("create", "ok", "Seite erstellt", mapping)
        return mapping
    except ConfluenceError as exc:
        message = friendly_message(exc)
    except PublishError as exc:
        message = str(exc)
    store.add_run(prepared.action, "error", message, prepared.mapping, source=prepared.doc.source,
                  source_id=prepared.doc.source_id, title=title)
    if prepared.mapping:
        store.save(prepared.mapping.model_copy(update={"last_error": message, "last_run_at": now()}))
    raise PublishError(message)


def _keep_confluence(store: Store, prepared: Prepared) -> Mapping:
    if prepared.mapping is None or prepared.page is None:
        raise PublishError("Es gibt keine Confluence-Seite, die behalten werden könnte.")
    mapping = prepared.mapping.model_copy(update={
        "published_version": prepared.page.version, "published_hash": content_hash(prepared.page.body or ""),
        "source_hash": prepared.doc.content_hash(),
        "source_edited_at": prepared.doc.source_edited_at.isoformat() if prepared.doc.source_edited_at else None,
        "status": planner.SYNCED, "last_run_at": now(), "last_error": None})
    mapping = store.save(mapping)
    store.add_run("keep", "ok", "Confluence-Version behalten", mapping)
    return mapping


def _update(store: Store, confluence, connector, prepared: Prepared, decision: str, title: str) -> Mapping:
    assert prepared.page is not None
    current = confluence.get_page(prepared.page.id)
    if current.version != prepared.page.version:
        raise PublishError("Die Seite wurde seit der Vorschau in Confluence geändert. Bitte die Vorschau neu laden.")
    if prepared.confluence_changed and decision != "overwrite":
        raise PublishError("Die Seite wurde in Confluence von Hand geändert. Bitte entscheiden: "
                           "Confluence-Version behalten oder mit Quelle überschreiben.")
    _upload_images(prepared, confluence, connector, prepared.page.id)
    confluence.update_page(prepared.page, title, prepared.storage)
    page = confluence.get_page(prepared.page.id, body=True)
    mapping = prepared.mapping
    return _remember(store, prepared, page, mapping.space if mapping else None,
                     mapping.parent_id if mapping else None, title)


def _create(store: Store, confluence, connector, prepared: Prepared, title: str, space: str,
            parent_id: str) -> Mapping:
    if not space:
        raise PublishError("Bitte einen Space in Confluence wählen.")
    if confluence.find_title(space, title):
        raise PublishError(f"Im Space {space} gibt es schon eine Seite «{title}». Bitte einen anderen Titel wählen.")
    created = confluence.create_page(space, parent_id or None, title, prepared.storage)
    _upload_images(prepared, confluence, connector, created.id)
    page = confluence.get_page(created.id, body=True)
    return _remember(store, prepared, page, space, parent_id, title)


# --------------------------------------------------------------------------- status check


def refresh_status(store: Store, confluence, connector, mapping: Mapping) -> Mapping:
    """Check one publication against source and Confluence and store the new status."""
    updates: dict = {"last_checked_at": now(), "last_error": None}
    source_changed = False
    if connector is None:
        updates["status"] = planner.UNKNOWN
        updates["last_error"] = "Quelle ist nicht verbunden."
        return store.save(mapping.model_copy(update=updates))
    try:
        info = connector.page_info(mapping.source_id)
        if info is None:
            return store.save(mapping.model_copy(update={**updates, "status": planner.SOURCE_MISSING}))
        edited = info.edited_at.isoformat() if info.edited_at else None
        if edited != mapping.source_edited_at:
            doc = connector.load(mapping.source_id)
            source_changed = doc.content_hash() != mapping.source_hash
            if not source_changed:
                updates["source_edited_at"] = edited
        try:
            page = confluence.get_page(mapping.confluence_page_id, body=True)
        except ConfluenceError as exc:
            if exc.status == 404:
                return store.save(mapping.model_copy(update={**updates, "status": planner.PAGE_MISSING}))
            raise
        changed = planner.confluence_changed(mapping, page)
        if not changed and page.version != mapping.published_version:
            updates["published_version"] = page.version
        updates["title"] = page.title
        updates["confluence_url"] = page.url
        updates["status"] = planner.decide(source_changed, changed)
    except ConfluenceError as exc:
        updates.update(status=planner.ERROR, last_error=friendly_message(exc))
    except SourceError as exc:
        updates.update(status=planner.ERROR, last_error=str(exc))
    return store.save(mapping.model_copy(update=updates))
