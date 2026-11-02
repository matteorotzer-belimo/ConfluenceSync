"""Decision logic: what happened on which side since the last publication (concept 8.2)."""
from __future__ import annotations

from ..confluence.checks import content_hash
from ..confluence.client import Page
from ..store import Mapping

SYNCED = "synced"                     # aktuell
SOURCE_CHANGED = "source_changed"     # Quelle geändert -> aktualisieren möglich
CONFLUENCE_CHANGED = "confluence_changed"  # in Confluence von Hand geändert
REVIEW = "review"                     # beide geändert -> Prüfung nötig
SOURCE_MISSING = "source_missing"     # Quelle gelöscht
PAGE_MISSING = "page_missing"         # Confluence-Seite gelöscht
ERROR = "error"
UNKNOWN = "unknown"                   # Quelle derzeit nicht verbunden

STATUS_LABELS = {
    SYNCED: "Aktuell",
    SOURCE_CHANGED: "Quelle geändert",
    CONFLUENCE_CHANGED: "In Confluence geändert",
    REVIEW: "Prüfung nötig",
    SOURCE_MISSING: "Quelle gelöscht",
    PAGE_MISSING: "Confluence-Seite fehlt",
    ERROR: "Fehler",
    UNKNOWN: "Nicht geprüft",
}


def confluence_changed(mapping: Mapping, page: Page) -> bool:
    """Changed by hand = newer version AND different content (title/label-only edits don't count)."""
    if mapping.published_version is not None and page.version == mapping.published_version:
        return False
    if page.body is None:
        raise ValueError("page body is required")
    return content_hash(page.body) != mapping.published_hash


def decide(source_changed: bool, confluence_was_changed: bool) -> str:
    if source_changed and confluence_was_changed:
        return REVIEW
    if confluence_was_changed:
        return CONFLUENCE_CHANGED
    if source_changed:
        return SOURCE_CHANGED
    return SYNCED
