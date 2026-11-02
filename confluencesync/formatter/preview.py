"""Content model -> HTML for the in-app preview (Qt QTextBrowser).

Qt supports only a subset of HTML/CSS, so panels and code blocks are tables with a background
colour. The result looks close to the Confluence page.
"""
from __future__ import annotations

from collections.abc import Callable
from html import escape

from ..model import (SOURCE_LABELS, BulletedList, Callout, Code, Divider, Heading, Image, Inline,
                     LinkToPage, NumberedList, Paragraph, Quote, SourceDocument, Table, TaskList,
                     Toggle, Unsupported)

CALLOUTS = {  # kind: (label, icon, background)
    "info": ("Info", "ℹ", "#deebff"),
    "note": ("Hinweis", "✎", "#eae6ff"),
    "tip": ("Tipp", "✔", "#e3fcef"),
    "warning": ("Warnung", "⚠", "#fffae6"),
}
STATUS_COLOURS = {  # colour: (background, text)
    "grey": ("#dfe1e6", "#42526e"), "blue": ("#deebff", "#0747a6"), "green": ("#e3fcef", "#006644"),
    "yellow": ("#fff0b3", "#172b4d"), "red": ("#ffebe6", "#bf2600"), "purple": ("#eae6ff", "#403294"),
}
MAX_IMAGE_WIDTH = 680
STYLE = """
body { color:#172b4d; font-family:'Segoe UI'; font-size:10.5pt; }
h1 { font-size:20pt; font-weight:600; margin-bottom:10px; }
h2 { font-size:15pt; font-weight:600; margin-top:18px; margin-bottom:6px; }
h3 { font-size:12.5pt; font-weight:600; margin-top:14px; margin-bottom:4px; }
h4 { font-size:11pt; font-weight:600; margin-top:12px; margin-bottom:4px; }
p { margin-top:4px; margin-bottom:4px; }
a { color:#0052cc; text-decoration:none; }
code { font-family:Consolas; background-color:#f4f5f7; }
pre { font-family:Consolas; font-size:9.5pt; margin:0; }
li { margin-top:2px; }
"""


def esc(text: str) -> str:
    return escape(text, quote=True)


def status_label(text: str, colour: str) -> str:
    bg, fg = STATUS_COLOURS.get((colour or "grey").lower(), STATUS_COLOURS["grey"])
    return (f'<span style="background-color:{bg}; color:{fg}; font-weight:700; font-size:8pt;">'
            f"&nbsp;{esc(text.upper())}&nbsp;</span>")


def inline(parts: list[Inline]) -> str:
    out = []
    for part in parts:
        if part.status:
            out.append(status_label(part.text, part.status))
            continue
        html = esc(part.text).replace("\n", "<br>")
        if part.code:
            html = f"<code>{html}</code>"
        if part.bold:
            html = f"<b>{html}</b>"
        if part.italic:
            html = f"<i>{html}</i>"
        if part.underline:
            html = f"<u>{html}</u>"
        if part.strike:
            html = f"<s>{html}</s>"
        if part.link:
            html = f'<a href="{esc(part.link)}">{html}</a>'
        out.append(html)
    return "".join(out)


def box(content: str, background: str, border: str | None = None) -> str:
    style = f"background-color:{background}; margin-top:8px; margin-bottom:8px;"
    if border:
        style += f" border:1px solid {border};"
    return (f'<table width="100%" cellspacing="0" cellpadding="9" style="{style}">'
            f"<tr><td>{content}</td></tr></table>")


class PreviewFormatter:
    def __init__(self, image_url: Callable[[Image], str]):
        self.image_url = image_url

    def document(self, doc: SourceDocument, with_title: bool = True) -> str:
        label = SOURCE_LABELS.get(doc.source, doc.source)
        source = f'<a href="{esc(doc.source_url)}">{esc(label)}</a>' if doc.source_url else esc(label)
        stand = f" · Stand: {doc.source_edited_at:%d.%m.%Y %H:%M}" if doc.source_edited_at else ""
        head = box(f"ℹ&nbsp; Erstellt mit ConfluenceSync aus {source}{stand} · "
                   "Änderungen bitte in der Quelle vornehmen.", CALLOUTS["info"][2])
        title = f"<h1>{esc(doc.title)}</h1>" if with_title else ""
        return f"<html><head><style>{STYLE}</style></head><body>{title}{head}{self.blocks(doc.blocks)}</body></html>"

    def blocks(self, blocks: list) -> str:
        return "".join(self.block(b) for b in blocks)

    def block(self, block) -> str:
        if isinstance(block, Heading):
            level = min(block.level + 1, 4)
            return f"<h{level}>{inline(block.text)}</h{level}>"
        if isinstance(block, Paragraph):
            return f"<p>{inline(block.text) or '&nbsp;'}</p>"
        if isinstance(block, (BulletedList, NumberedList)):
            tag = "ul" if isinstance(block, BulletedList) else "ol"
            items = "".join(f"<li>{inline(i.text)}{self.blocks(i.children)}</li>" for i in block.items)
            return f"<{tag}>{items}</{tag}>"
        if isinstance(block, TaskList):
            rows = []
            for item in block.items:
                text = inline(item.text)
                if item.done:
                    text = f'<s style="color:#6b778c">{text}</s>'
                mark = '<span style="color:#0052cc">☑</span>' if item.done else "☐"
                rows.append(f'<tr><td width="22" valign="top">{mark}</td><td>{text}{self.blocks(item.children)}</td></tr>')
            return f'<table cellspacing="0" cellpadding="2" style="margin-top:4px; margin-bottom:4px;">{"".join(rows)}</table>'
        if isinstance(block, Quote):
            return f'<blockquote style="color:#42526e">{self.blocks(block.children)}</blockquote>'
        if isinstance(block, Callout):
            _, icon, background = CALLOUTS[block.kind]
            title = f"<b>{icon}&nbsp; {esc(block.title)}</b>" if block.title else f"<b>{icon}</b>"
            return box(title + self.blocks(block.children), background)
        if isinstance(block, Code):
            lang = (f'<span style="color:#6b778c; font-size:8pt">{esc(block.language.upper())}</span><br>'
                    if block.language else "")
            return box(f"{lang}<pre>{esc(block.code)}</pre>", "#f4f5f7", "#dfe1e6")
        if isinstance(block, Table):
            rows = []
            for index, row in enumerate(block.rows):
                header = block.header_row and index == 0
                tag = "th" if header else "td"
                bg = ' bgcolor="#f4f5f7"' if header else ""
                rows.append("<tr>" + "".join(f'<{tag}{bg} valign="top" align="left">{self.blocks(c.children)}</{tag}>'
                                             for c in row) + "</tr>")
            return ('<table border="1" cellspacing="0" cellpadding="6" '
                    'style="border-color:#c1c7d0; border-style:solid; margin-top:8px; margin-bottom:8px;">'
                    f'{"".join(rows)}</table>')
        if isinstance(block, Divider):
            return "<hr>"
        if isinstance(block, Toggle):
            title = f'<span style="color:#0052cc">▾ {esc(block.title or "Details")}</span>'
            return box(title + self.blocks(block.children), "#ffffff", "#dfe1e6")
        if isinstance(block, Image):
            width = min(block.width or MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH)
            caption = f'<br><span style="color:#6b778c; font-size:9pt">{inline(block.caption)}</span>' if block.caption else ""
            return (f'<p><img src="{esc(self.image_url(block))}" width="{width}" alt="{esc(block.alt or "")}">'
                    f"{caption}</p>")
        if isinstance(block, LinkToPage):
            if block.url:
                return f'<p>↗ <a href="{esc(block.url)}">{esc(block.title)}</a></p>'
            return f"<p>{esc(block.title)}</p>"
        if isinstance(block, Unsupported):
            return box(f"<b>✎&nbsp; Nicht übertragen</b><br>{esc(block.note)}", CALLOUTS["note"][2], "#8777d9")
        raise TypeError(f"unknown block type: {type(block).__name__}")


def to_preview_html(doc: SourceDocument, image_url: Callable[[Image], str], with_title: bool = True) -> str:
    return PreviewFormatter(image_url).document(doc, with_title)
