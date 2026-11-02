from __future__ import annotations

from conftest import make_doc

from confluencesync.formatter.preview import to_preview_html
from confluencesync.model import (Callout, Code, Image, Inline, Paragraph, TaskItem, TaskList, Unsupported)


def test_preview_contains_title_header_and_blocks():
    doc = make_doc([Paragraph(text=[Inline(text="Hallo <Welt>", bold=True)]),
                    Callout(kind="warning", title="Vorsicht", children=[Paragraph(text=[Inline(text="heiss")])]),
                    Code(language="python", code="x = 1 < 2"),
                    TaskList(items=[TaskItem(done=True, text=[Inline(text="fertig")])])],
                   title="Mein Titel & mehr")
    html = to_preview_html(doc, lambda img: "unused")
    assert html.startswith("<html>") and html.endswith("</html>")
    assert "<h1>Mein Titel &amp; mehr</h1>" in html
    assert "Erstellt mit ConfluenceSync aus" in html
    assert 'href="https://example.com/note?a=1&amp;b=2"' in html
    assert "Stand: 28.10.2026 09:30" in html
    assert "<b>Hallo &lt;Welt&gt;</b>" in html
    assert "Vorsicht" in html and "#fffae6" in html
    assert "PYTHON" in html and "x = 1 &lt; 2" in html
    assert "☑" in html and "<s " in html


def test_preview_without_title():
    html = to_preview_html(make_doc([], title="Ohne"), lambda img: "", with_title=False)
    assert "<h1>" not in html
    assert "Erstellt mit ConfluenceSync" in html


def test_preview_renders_unsupported_note():
    doc = make_doc([Unsupported(source_type="notion:embed", note="Video <x> fehlt")])
    html = to_preview_html(doc, lambda img: "")
    assert "Nicht übertragen" in html
    assert "Video &lt;x&gt; fehlt" in html


def test_preview_uses_image_callback():
    image = Image(ref="notion:abc", mime="image/png", alt="Diagramm", width=2000,
                  caption=[Inline(text="Bildunterschrift")])
    seen = []

    def url(img: Image) -> str:
        seen.append(img)
        return f"csimg:{img.filename}"

    html = to_preview_html(make_doc([image]), url)
    assert seen == [image]
    assert f'src="csimg:{image.filename}"' in html
    assert 'width="680"' in html          # capped to the preview width
    assert 'alt="Diagramm"' in html
    assert "Bildunterschrift" in html
