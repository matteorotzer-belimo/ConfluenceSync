from __future__ import annotations

import pytest

from confluencesync.confluence.checks import (StorageError, check_generated, content_hash, lost_items,
                                              parse_storage, protected_items)

JIRA = ('<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">ABC-1</ac:parameter>'
        "</ac:structured-macro>")
HAND_IMAGE = '<ac:image><ri:attachment ri:filename="screenshot.png" /></ac:image>'
URL_IMAGE = '<ac:image><ri:url ri:value="https://example.com/logo.png" /></ac:image>'
OWN_IMAGE = '<ac:image><ri:attachment ri:filename="cs-0123456789ab.png" /></ac:image>'
ATTACHMENT_LINK = '<ac:link><ri:attachment ri:filename="Vertrag.pdf" /></ac:link>'
OWN_ATTACHMENT_LINK = '<ac:link><ri:attachment ri:filename="cs-file.pdf" /></ac:link>'
COMMENT = '<ac:inline-comment-marker ac:ref="c-42">markiert</ac:inline-comment-marker>'
INFO = ('<ac:structured-macro ac:name="info"><ac:rich-text-body><p>x</p></ac:rich-text-body>'
        "</ac:structured-macro>")


def kinds(storage: str) -> list[tuple[str, str]]:
    return sorted((kind, name) for kind, name, _ in protected_items(parse_storage(storage)))


def test_protected_items_detects_foreign_content_only():
    body = f"<p>{COMMENT}</p>{JIRA}{INFO}<p>{HAND_IMAGE}{URL_IMAGE}{OWN_IMAGE}</p><p>{ATTACHMENT_LINK}{OWN_ATTACHMENT_LINK}</p>"
    assert kinds(body) == [("attachment", "Vertrag.pdf"), ("comment", "c-42"),
                           ("image", "https://example.com/logo.png"), ("image", "screenshot.png"),
                           ("macro", "jira")]


def test_protected_items_counts_duplicates():
    items = protected_items(parse_storage(JIRA + JIRA))
    assert sum(items.values()) == 2


def test_lost_items_lists_removed_protected_content():
    current = f"<p>Alt {COMMENT}</p>{JIRA}<p>{HAND_IMAGE}</p><p>{ATTACHMENT_LINK}</p><p>{OWN_IMAGE}</p>"
    new = "<p>Neu</p>"
    lost = lost_items(current, new)
    assert lost == ["Inline-Kommentar", "App-Makro «jira»", "Bild «screenshot.png» (von Hand eingefügt)",
                    "Link auf Anhang «Vertrag.pdf»"]


def test_lost_items_ignores_items_that_are_kept():
    current = f"<p>Alt</p>{JIRA}"
    assert lost_items(current, f"<p>Neu</p>{JIRA}") == []
    changed = JIRA.replace("ABC-1", "ABC-2")
    assert lost_items(current, f"<p>Neu</p>{changed}") == ["App-Makro «jira»"]


def test_lost_items_with_unparsable_current_page():
    assert lost_items("<p>kaputt", "<p>neu</p>") == []


def test_parse_storage_accepts_html_entities_and_rejects_broken_xml():
    root = parse_storage("<p>a&nbsp;b &amp; c&hellip;</p>")
    assert "".join(root.itertext()) == "a\xa0b & c…"
    with pytest.raises(StorageError):
        parse_storage("<p><b>falsch</p></b>")
    with pytest.raises(StorageError):
        parse_storage("<p>&unknownentity;</p>")


def test_check_generated():
    assert check_generated("") == ["Die Seite ist leer."]
    assert check_generated("   ") == ["Die Seite ist leer."]
    assert check_generated(f"<p>ok</p>{INFO}") == []
    broken = check_generated("<p>offen")
    assert len(broken) == 1 and broken[0].startswith("kein gültiges Storage-Format")
    assert check_generated(JIRA + JIRA) == ["Makro «jira» ist nicht erlaubt."]
    assert check_generated(f"<p>{COMMENT}</p>") == ["Inline-Kommentare können nur in Confluence erstellt werden."]


def test_content_hash_ignores_line_endings_and_whitespace_between_tags():
    a = "<p>eins</p>\n<p>zwei</p>"
    b = "  <p>eins</p>\r\n   <p>zwei</p>\n"
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash("<p>eins</p><p>drei</p>")
    assert content_hash("<p>a b</p>") != content_hash("<p>a  b</p>")
