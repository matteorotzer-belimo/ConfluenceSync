from __future__ import annotations

import pytest

from confluencesync.confluence.checks import content_hash
from confluencesync.confluence.client import Page
from confluencesync.store import Mapping
from confluencesync.sync import planner

BODY = "<p>Veröffentlicht</p>"


def mapping(version: int | None = 3, body: str = BODY) -> Mapping:
    return Mapping(source="demo", source_id="x", confluence_page_id="1", published_version=version,
                   published_hash=content_hash(body))


def page(version: int, body: str | None) -> Page:
    return Page("1", "Titel", version, body=body)


@pytest.mark.parametrize("source_changed,confluence_changed,expected", [
    (False, False, planner.SYNCED),
    (True, False, planner.SOURCE_CHANGED),
    (False, True, planner.CONFLUENCE_CHANGED),
    (True, True, planner.REVIEW),
])
def test_decide(source_changed, confluence_changed, expected):
    assert planner.decide(source_changed, confluence_changed) == expected


def test_status_labels_cover_all_statuses():
    statuses = {planner.SYNCED, planner.SOURCE_CHANGED, planner.CONFLUENCE_CHANGED, planner.REVIEW,
                planner.SOURCE_MISSING, planner.PAGE_MISSING, planner.ERROR, planner.UNKNOWN}
    assert statuses == set(planner.STATUS_LABELS)


def test_same_version_is_never_a_manual_change():
    assert planner.confluence_changed(mapping(3), page(3, "<p>ganz anders</p>")) is False
    assert planner.confluence_changed(mapping(3), page(3, None)) is False


def test_new_version_with_same_content_is_not_a_manual_change():
    # e.g. only the title or a label was changed, or whitespace/line endings differ
    assert planner.confluence_changed(mapping(3), page(4, BODY)) is False
    assert planner.confluence_changed(mapping(3), page(5, "\r\n" + BODY + "\n")) is False


def test_new_version_with_different_content_is_a_manual_change():
    assert planner.confluence_changed(mapping(3), page(4, BODY + "<p>Von Hand</p>")) is True


def test_unknown_published_version_compares_content():
    assert planner.confluence_changed(mapping(None), page(1, BODY)) is False
    assert planner.confluence_changed(mapping(None), page(1, "<p>anders</p>")) is True


def test_body_is_required_when_version_differs():
    with pytest.raises(ValueError):
        planner.confluence_changed(mapping(3), page(4, None))
