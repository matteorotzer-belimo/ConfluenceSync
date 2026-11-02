from __future__ import annotations

import pytest

from confluencesync.connectors.onenote_html import parse_onenote_html
from confluencesync.model import (BulletedList, Code, Heading, Image, NumberedList, Paragraph, Table, TaskList,
                                  Unsupported, plain)

PAGE = """<html><head><title>Synthetische Seite</title></head>
<body data-absolute-enabled="true">
<div style="position:absolute;left:48px;top:400px;width:600px">
  <h3>Unten</h3>
  <p>Anhang folgt:</p>
  <object data-attachment="Bericht.pdf" type="application/pdf" data="https://graph.microsoft.com/x"></object>
  <iframe src="https://video.example.com/v"></iframe>
</div>
<div style="position:absolute;left:48px;top:100px;width:600px">
  <h1>Titel <span style="font-weight:bold">eins</span></h1>
  <h2>Zwei</h2>
  <p>Normal <span style="font-weight:bold">fett</span> und <span style="font-style:italic">kursiv</span>
     und <a href="https://example.com/x">Link</a> und <span style="font-family:Consolas">mono</span>.</p>
  <ul>
    <li>Punkt A
      <ul><li>Unterpunkt A1</li></ul>
    </li>
    <li>Punkt B</li>
    <ol><li>Nummer 1</li></ol>
  </ul>
  <ol><li><p>Erster Schritt</p></li><li>Zweiter Schritt</li></ol>
  <p data-tag="to-do">Offene Aufgabe</p>
  <p data-tag="to-do:completed">Erledigte Aufgabe</p>
  <p data-tag="important">Wichtiger Satz</p>
  <table>
    <tr><th>Kopf 1</th><th>Kopf 2</th></tr>
    <tr><td><p>Zelle <b>1</b></p></td><td>Zelle 2</td></tr>
  </table>
  <pre>def f():
    return 1</pre>
  <img src="https://graph.microsoft.com/v1.0/low" data-fullres-src="https://graph.microsoft.com/v1.0/full"
       data-fullres-src-type="image/jpeg" width="400" alt="Foto" />
</div>
<div style="position:absolute;left:700px;top:100px;width:200px">
  <p>Rechts daneben</p>
</div>
</body></html>"""


@pytest.fixture(scope="module")
def parsed():
    return parse_onenote_html(PAGE)


@pytest.fixture(scope="module")
def blocks(parsed):
    return parsed[1]


def of(blocks, cls):
    return [b for b in blocks if isinstance(b, cls)]


def test_title(parsed):
    assert parsed[0] == "Synthetische Seite"


def test_containers_are_ordered_top_to_bottom_then_left_to_right(blocks):
    headings = [plain(h.text) for h in of(blocks, Heading)]
    assert headings == ["Titel eins", "Zwei", "Unten"]
    texts = [plain(p.text) for p in of(blocks, Paragraph)]
    assert texts.index("Rechts daneben") < texts.index("Anhang folgt:")
    assert isinstance(blocks[-1], Unsupported)


def test_heading_levels(blocks):
    assert [h.level for h in of(blocks, Heading)] == [1, 2, 3]
    first = of(blocks, Heading)[0]
    assert any(part.bold and part.text == "eins" for part in first.text)


def test_inline_styles_from_spans(blocks):
    para = next(p for p in of(blocks, Paragraph) if plain(p.text).startswith("Normal"))
    parts = {part.text: part for part in para.text}
    assert parts["fett"].bold and not parts["fett"].italic
    assert parts["kursiv"].italic and not parts["kursiv"].bold
    assert parts["Link"].link == "https://example.com/x"
    assert parts["mono"].code
    assert plain(para.text) == "Normal fett und kursiv und Link und mono."


def test_nested_lists(blocks):
    bullets = of(blocks, BulletedList)[0]
    assert [plain(i.text) for i in bullets.items] == ["Punkt A", "Punkt B"]
    nested = bullets.items[0].children[0]
    assert isinstance(nested, BulletedList) and plain(nested.items[0].text) == "Unterpunkt A1"
    sibling_ol = bullets.items[1].children[0]
    assert isinstance(sibling_ol, NumberedList) and plain(sibling_ol.items[0].text) == "Nummer 1"
    numbered = of(blocks, NumberedList)[0]
    assert [plain(i.text) for i in numbered.items] == ["Erster Schritt", "Zweiter Schritt"]


def test_tasks_are_merged_into_one_task_list(blocks):
    tasks = of(blocks, TaskList)
    assert len(tasks) == 1
    assert [(plain(i.text), i.done) for i in tasks[0].items] == [("Offene Aufgabe", False),
                                                                ("Erledigte Aufgabe", True)]


def test_note_tags_become_status_labels(blocks):
    para = next(p for p in of(blocks, Paragraph) if "Wichtiger Satz" in plain(p.text))
    assert para.text[0].status == "Red" and para.text[0].text == "WICHTIG"


def test_table(blocks):
    table = of(blocks, Table)[0]
    assert table.header_row
    assert len(table.rows) == 2
    assert plain(table.rows[0][0].children[0].text) == "Kopf 1"
    cell = table.rows[1][0].children[0]
    assert plain(cell.text) == "Zelle 1" and cell.text[-1].bold


def test_pre_becomes_code(blocks):
    code = of(blocks, Code)[0]
    assert code.code == "def f():\n    return 1"


def test_image_uses_fullres_source(blocks):
    image = of(blocks, Image)[0]
    assert image.ref == "https://graph.microsoft.com/v1.0/full"
    assert image.mime == "image/jpeg"
    assert image.width == 400
    assert image.alt == "Foto"
    assert image.filename.endswith(".jpg")


def test_attachment_and_embed_become_unsupported(blocks):
    items = of(blocks, Unsupported)
    assert [u.source_type for u in items] == ["onenote:attachment", "onenote:embed"]
    assert "Bericht.pdf" in items[0].note


def test_page_without_absolute_positioning_and_without_title():
    title, blocks = parse_onenote_html("<html><body><p>Nur Text</p><img src='' /></body></html>")
    assert title == ""
    assert len(blocks) == 1 and plain(blocks[0].text) == "Nur Text"


def test_list_item_with_todo_tag_gets_checkbox_mark():
    _, blocks = parse_onenote_html('<body><ul><li data-tag="to-do:completed">Erledigt</li>'
                                   '<li data-tag="to-do">Offen</li></ul></body>')
    assert [plain(i.text) for i in blocks[0].items] == ["☑ Erledigt", "☐ Offen"]
