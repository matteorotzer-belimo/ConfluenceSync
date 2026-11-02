from __future__ import annotations

import pytest

from confluencesync.connectors.notion_blocks import convert, page_url, rich_text
from confluencesync.model import (BulletedList, Callout, Code, Divider, Heading, Image, LinkToPage, NumberedList,
                                  Paragraph, Quote, Table, TaskList, Toggle, Unsupported, plain)


def rt(text, href=None, **annotations):
    return {"type": "text", "plain_text": text, "href": href,
            "text": {"content": text, "link": {"url": href} if href else None},
            "annotations": {"bold": False, "italic": False, "strikethrough": False, "underline": False,
                            "code": False, "color": "default", **annotations}}


def block(btype, block_id="b", children=None, **data):
    out = {"object": "block", "id": block_id, "type": btype, "has_children": bool(children), btype: data}
    if children:
        out["children"] = children
    return out


def test_rich_text_annotations_and_links():
    parts = rich_text([rt("fett", bold=True), rt("kursiv", italic=True), rt("unter", underline=True),
                       rt("durch", strikethrough=True), rt("code", code=True), rt("Link", href="https://e.com"),
                       rt("intern", href="/abc123"), rt("")])
    assert [p.text for p in parts] == ["fett", "kursiv", "unter", "durch", "code", "Link", "intern"]
    assert parts[0].bold and parts[1].italic and parts[2].underline and parts[3].strike and parts[4].code
    assert parts[5].link == "https://e.com"
    assert parts[6].link == "https://www.notion.so/abc123"
    assert rich_text([{"text": {"content": "ohne plain"}}])[0].text == "ohne plain"


def test_paragraph_and_headings():
    blocks = convert([
        block("heading_1", rich_text=[rt("H1")]),
        block("heading_2", rich_text=[rt("H2")]),
        block("heading_3", rich_text=[rt("H3")]),
        block("paragraph", rich_text=[rt("Text "), rt("fett", bold=True)]),
        block("paragraph", rich_text=[]),
        block("heading_2", rich_text=[]),
    ])
    assert [(type(b), getattr(b, "level", None)) for b in blocks] == [
        (Heading, 1), (Heading, 2), (Heading, 3), (Paragraph, None)]
    assert plain(blocks[3].text) == "Text fett" and blocks[3].text[1].bold


def test_toggleable_heading_keeps_children_after_heading():
    blocks = convert([block("heading_2", is_toggleable=True, rich_text=[rt("Aufklappbar")],
                            children=[block("paragraph", rich_text=[rt("innen")])])])
    assert isinstance(blocks[0], Heading) and isinstance(blocks[1], Paragraph)


def test_list_items_are_grouped_with_children():
    blocks = convert([
        block("bulleted_list_item", "1", rich_text=[rt("a")],
              children=[block("numbered_list_item", "1a", rich_text=[rt("a.1")])]),
        block("bulleted_list_item", "2", rich_text=[rt("b")]),
        block("numbered_list_item", "3", rich_text=[rt("eins")]),
        block("numbered_list_item", "4", rich_text=[rt("zwei")]),
    ])
    assert [type(b) for b in blocks] == [BulletedList, NumberedList]
    assert [plain(i.text) for i in blocks[0].items] == ["a", "b"]
    nested = blocks[0].items[0].children[0]
    assert isinstance(nested, NumberedList) and plain(nested.items[0].text) == "a.1"
    assert [plain(i.text) for i in blocks[1].items] == ["eins", "zwei"]


def test_to_do_items():
    blocks = convert([block("to_do", "1", rich_text=[rt("offen")], checked=False),
                      block("to_do", "2", rich_text=[rt("fertig")], checked=True,
                            children=[block("paragraph", rich_text=[rt("Notiz")])])])
    assert len(blocks) == 1 and isinstance(blocks[0], TaskList)
    assert [(plain(i.text), i.done) for i in blocks[0].items] == [("offen", False), ("fertig", True)]
    assert isinstance(blocks[0].items[1].children[0], Paragraph)


@pytest.mark.parametrize("icon,color,kind", [
    ({"type": "emoji", "emoji": "⚠️"}, "default", "warning"),
    ({"type": "emoji", "emoji": "💡"}, "default", "tip"),
    ({"type": "emoji", "emoji": "📝"}, "default", "note"),
    (None, "red_background", "warning"),
    (None, "green_background", "tip"),
    (None, "yellow_background", "note"),
    (None, "gray_background", "info"),
])
def test_callout_kind(icon, color, kind):
    blocks = convert([block("callout", rich_text=[rt("Hinweistext")], icon=icon, color=color)])
    callout = blocks[0]
    assert isinstance(callout, Callout) and callout.kind == kind
    assert plain(callout.children[0].text) == "Hinweistext"


def test_code_quote_divider_equation_bookmark():
    blocks = convert([
        block("code", rich_text=[rt("echo hi")], language="shell"),
        block("code", rich_text=[rt("plain")], language="plain text"),
        block("quote", rich_text=[rt("Zitat")]),
        block("divider"),
        block("equation", expression="E=mc^2"),
        block("bookmark", url="https://example.com", caption=[]),
    ])
    assert isinstance(blocks[0], Code) and blocks[0].language == "bash" and blocks[0].code == "echo hi"
    assert blocks[1].language is None
    assert isinstance(blocks[2], Quote) and plain(blocks[2].children[0].text) == "Zitat"
    assert isinstance(blocks[3], Divider)
    assert blocks[4].text[0].code and blocks[4].text[0].text == "E=mc^2"
    assert blocks[5].text[0].link == "https://example.com"


def test_table_with_rows():
    rows = [block("table_row", f"r{i}", cells=[[rt(f"{i}-a")], [rt(f"{i}-b")], []]) for i in range(2)]
    blocks = convert([block("table", "t", children=rows, table_width=3, has_column_header=True)])
    table = blocks[0]
    assert isinstance(table, Table) and table.header_row
    assert len(table.rows) == 2 and len(table.rows[0]) == 3
    assert plain(table.rows[1][1].children[0].text) == "1-b"
    assert table.rows[0][2].children == []


def test_images_file_and_external():
    blocks = convert([
        block("image", "img-1", type="file", file={"url": "https://s3.example.com/a/photo.jpg?sig=1"},
              caption=[rt("Foto")]),
        block("image", "img-2", type="external", external={"url": "https://cdn.example.com/x.gif"}),
    ])
    first, second = blocks
    assert isinstance(first, Image) and isinstance(second, Image)
    assert first.ref == "notion:img-1" and first.mime == "image/jpeg"
    assert first.download_url == "https://s3.example.com/a/photo.jpg?sig=1"
    assert first.alt == "Foto" and plain(first.caption) == "Foto"
    assert second.ref == "notion:img-2" and second.mime == "image/gif" and second.alt is None
    # the short-lived URL must not end up in the content hash
    assert "download_url" not in first.model_dump()


def test_toggle_and_child_page():
    blocks = convert([
        block("toggle", rich_text=[rt("Mehr")], children=[block("paragraph", rich_text=[rt("versteckt")])]),
        block("child_page", "1234-5678", title="Unterseite A"),
    ])
    assert isinstance(blocks[0], Toggle) and blocks[0].title == "Mehr"
    assert plain(blocks[0].children[0].text) == "versteckt"
    assert isinstance(blocks[1], LinkToPage) and blocks[1].url == page_url("1234-5678")
    assert blocks[1].url == "https://www.notion.so/12345678"


def test_unsupported_blocks_are_never_dropped_silently():
    blocks = convert([
        block("fancy_new_widget"),
        block("child_database", title="Aufgaben"),
        block("file", name="bericht.pdf"),
        block("embed", url="https://youtube.example.com/v"),
        block("synced_block"),
        block("table_of_contents"),
    ])
    assert all(isinstance(b, Unsupported) for b in blocks)
    assert [b.source_type for b in blocks] == ["notion:fancy_new_widget", "notion:child_database",
                                               "notion:file", "notion:embed", "notion:synced_block"]
    assert "fancy_new_widget" in blocks[0].note
    assert "Aufgaben" in blocks[1].note
    assert "bericht.pdf" in blocks[2].note


def test_columns_are_flattened():
    blocks = convert([block("column_list", children=[
        block("column", "c1", children=[block("paragraph", rich_text=[rt("links")])]),
        block("column", "c2", children=[block("paragraph", rich_text=[rt("rechts")])])])])
    assert [plain(b.text) for b in blocks] == ["links", "rechts"]
