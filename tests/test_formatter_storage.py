from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from conftest import make_doc

from confluencesync.confluence.checks import NS, check_generated, parse_storage, q
from confluencesync.formatter.storage import inline, to_storage
from confluencesync.model import (BulletedList, Callout, Code, Divider, Heading, Image, Inline, LinkToPage,
                                  ListItem, NumberedList, Paragraph, Quote, Table, TableCell, TaskItem,
                                  TaskList, Toggle, Unsupported)


def parse(storage: str) -> ET.Element:
    """Parse with a plain XML parser, namespaces declared on a wrapper root."""
    ns = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
    return ET.fromstring(f"<root {ns}>{storage}</root>")


def macros(root: ET.Element, name: str) -> list[ET.Element]:
    return [m for m in root.iter(q("ac:structured-macro")) if m.get(q("ac:name")) == name]


def full_doc():
    return make_doc([
        Heading(level=1, text=[Inline(text="Ziele")]),
        Heading(level=2, text=[Inline(text="Unterziel")]),
        Heading(level=3, text=[Inline(text="Detail")]),
        Paragraph(text=[Inline(text="fett", bold=True), Inline(text=" "), Inline(text="kursiv", italic=True),
                        Inline(text=" "), Inline(text="Link", link="https://example.com/?x=1&y=2"),
                        Inline(text=" "), Inline(text="code()", code=True),
                        Inline(text=" a < b & c > d")]),
        BulletedList(items=[ListItem(text=[Inline(text="eins")]),
                            ListItem(text=[Inline(text="zwei")], children=[
                                NumberedList(items=[ListItem(text=[Inline(text="zwei.a")])])])]),
        TaskList(items=[TaskItem(done=False, text=[Inline(text="offen")]),
                        TaskItem(done=True, text=[Inline(text="erledigt")])]),
        Table(header_row=True, rows=[
            [TableCell(children=[Paragraph(text=[Inline(text="Kopf A")])]),
             TableCell(children=[Paragraph(text=[Inline(text="Kopf B")])])],
            [TableCell(children=[Paragraph(text=[Inline(text="a1")])]),
             TableCell(children=[Paragraph(text=[Inline(text="b1")])])]]),
        Callout(kind="info", children=[Paragraph(text=[Inline(text="Info")])]),
        Callout(kind="note", title="Notiz", children=[Paragraph(text=[Inline(text="Hinweis")])]),
        Callout(kind="tip", children=[Paragraph(text=[Inline(text="Tipp")])]),
        Callout(kind="warning", children=[Paragraph(text=[Inline(text="Achtung")])]),
        Code(language="python", code="if a < b and c > d: print('&') # ]]> end"),
        Divider(),
        Quote(children=[Paragraph(text=[Inline(text="Zitat")])]),
        Toggle(title="Mehr", children=[Paragraph(text=[Inline(text="versteckt")])]),
        Image(ref="https://graph.microsoft.com/img/1", mime="image/jpeg", alt="Bild <1>", width=320,
              caption=[Inline(text="Legende")]),
        LinkToPage(title="Andere Seite", url="https://www.notion.so/abc"),
        Unsupported(source_type="onenote:attachment", note="Dateianhang «x.pdf» wurde nicht übertragen."),
    ])


@pytest.fixture
def storage():
    return to_storage(full_doc())


@pytest.fixture
def root(storage):
    return parse(storage)


def test_output_is_well_formed_and_passes_checks(storage):
    parse(storage)
    parse_storage(storage)
    assert check_generated(storage) == []


def test_info_panel_is_first_with_source_label_link_and_date(root):
    first = list(root)[0]
    assert first.tag == q("ac:structured-macro")
    assert first.get(q("ac:name")) == "info"
    text = "".join(first.itertext())
    assert "Erstellt mit ConfluenceSync aus Beispielnotizen" in text
    assert "Stand: 28.10.2026 09:30" in text
    link = first.find(".//a")
    assert link is not None and link.get("href") == "https://example.com/note?a=1&b=2"


def test_header_without_url_and_without_header():
    doc = make_doc([Paragraph(text=[Inline(text="x")])], source="notion", source_url=None, source_edited_at=None)
    out = to_storage(doc)
    root = parse(out)
    text = "".join(list(root)[0].itertext())
    assert "aus Notion" in text and "Stand" not in text
    assert list(root)[0].find(".//a") is None
    assert to_storage(doc, with_header=False) == "<p>x</p>"


def test_headings_are_shifted_by_one_level(root):
    assert [h.text for h in root.iter("h2")] == ["Ziele"]
    assert [h.text for h in root.iter("h3")] == ["Unterziel"]
    assert [h.text for h in root.iter("h4")] == ["Detail"]
    assert next(root.iter("h1"), None) is None


def test_inline_formatting(storage, root):
    assert "<strong>fett</strong>" in storage
    assert "<em>kursiv</em>" in storage
    assert "<code>code()</code>" in storage
    link = next(a for a in root.iter("a") if a.text == "Link")
    assert link.get("href") == "https://example.com/?x=1&y=2"
    assert 'href="https://example.com/?x=1&amp;y=2"' in storage


def test_text_is_xml_escaped(storage, root):
    assert " a &lt; b &amp; c &gt; d" in storage
    para = next(p for p in root.iter("p") if "fett" in "".join(p.itertext()))
    assert "".join(para.itertext()).endswith("a < b & c > d")


def test_inline_combined_formats_and_line_breaks():
    html = inline([Inline(text="x\ny", bold=True, italic=True, underline=True, strike=True,
                          link="https://e.com")])
    assert html == '<a href="https://e.com"><s><u><em><strong>x<br />y</strong></em></u></s></a>'
    assert inline([Inline(text="")]) == ""
    status = inline([Inline(text="WICHTIG", status="Red")])
    assert 'ac:name="status"' in status and ">Red<" in status and ">WICHTIG<" in status


def test_nested_lists(root):
    ul = next(root.iter("ul"))
    items = list(ul)
    assert [li.text for li in items] == ["eins", "zwei"]
    nested = items[1].find("ol")
    assert nested is not None and nested.find("li").text == "zwei.a"


def test_task_list(root):
    tasks = list(next(root.iter(q("ac:task-list"))))
    assert len(tasks) == 2
    assert [t.find(q("ac:task-status")).text for t in tasks] == ["incomplete", "complete"]
    assert [t.find(q("ac:task-body")).text for t in tasks] == ["offen", "erledigt"]
    assert [t.find(q("ac:task-id")).text for t in tasks] == ["1", "2"]


def test_task_with_children_stays_well_formed():
    doc = make_doc([TaskList(items=[
        TaskItem(text=[Inline(text="a")], children=[Paragraph(text=[Inline(text="Unterpunkt")])]),
        TaskItem(text=[Inline(text="b")], children=[Paragraph(text=[Inline(text="Ende")])])])])
    out = to_storage(doc, with_header=False)
    root = parse(out)
    assert "<ac:task-list></ac:task-list>" not in out
    assert len(list(root.iter(q("ac:task")))) == 2
    assert [p.text for p in root.findall("p")] == ["Unterpunkt", "Ende"]
    assert check_generated(out) == []


def test_table_with_header_row(root):
    rows = list(next(root.iter("table")).find("tbody"))
    assert [c.tag for c in rows[0]] == ["th", "th"]
    assert [c.tag for c in rows[1]] == ["td", "td"]
    assert "".join(rows[1][1].itertext()) == "b1"


@pytest.mark.parametrize("kind,text", [("info", "Info"), ("note", "Hinweis"), ("tip", "Tipp"),
                                       ("warning", "Achtung")])
def test_callouts_become_panels(root, kind, text):
    bodies = ["".join(m.find(q("ac:rich-text-body")).itertext()) for m in macros(root, kind)]
    assert text in bodies


def test_callout_title_parameter(root):
    note = next(m for m in macros(root, "note") if "Hinweis" in "".join(m.itertext()))
    param = note.find(q("ac:parameter"))
    assert param.get(q("ac:name")) == "title" and param.text == "Notiz"


def test_code_macro_with_language_and_cdata(root):
    code = macros(root, "code")[0]
    lang = code.find(q("ac:parameter"))
    assert lang.get(q("ac:name")) == "language" and lang.text == "python"
    assert code.find(q("ac:plain-text-body")).text == "if a < b and c > d: print('&') # ]]> end"


def test_divider_quote_toggle_and_link(root):
    assert next(root.iter("hr"), None) is not None
    assert "".join(next(root.iter("blockquote")).itertext()) == "Zitat"
    expand = macros(root, "expand")[0]
    assert expand.find(q("ac:parameter")).text == "Mehr"
    assert "versteckt" in "".join(expand.itertext())
    assert any(a.get("href") == "https://www.notion.so/abc" and a.text == "Andere Seite" for a in root.iter("a"))


def test_image_becomes_attachment(root):
    image_block = full_doc().blocks[15]
    img = next(root.iter(q("ac:image")))
    assert img.get(q("ac:alt")) == "Bild <1>"
    assert img.get(q("ac:width")) == "320"
    att = img.find(q("ri:attachment"))
    assert att.get(q("ri:filename")) == image_block.filename
    assert image_block.filename.startswith("cs-") and image_block.filename.endswith(".jpg")
    assert any("".join(e.itertext()) == "Legende" for e in root.iter("em"))


def test_unsupported_block_is_visible_note(root):
    notes = [m for m in macros(root, "note") if "x.pdf" in "".join(m.itertext())]
    assert len(notes) == 1
    assert notes[0].find(q("ac:parameter")).text == "Nicht übertragen"


def test_empty_callout_and_toggle_get_empty_paragraph():
    out = to_storage(make_doc([Callout(kind="tip", children=[]), Toggle(title="", children=[])]),
                     with_header=False)
    assert out.count("<ac:rich-text-body><p></p></ac:rich-text-body>") == 2
    assert '<ac:parameter ac:name="title">Details</ac:parameter>' in out


def test_unknown_block_type_raises():
    from confluencesync.formatter.storage import StorageFormatter

    with pytest.raises(TypeError):
        StorageFormatter().block(object())
