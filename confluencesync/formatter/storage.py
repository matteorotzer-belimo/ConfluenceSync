"""Content model -> Confluence storage format (XHTML with ac:/ri: elements).

Only uses the design elements allowed in the team's Confluence guidelines: headings h2-h4,
paragraphs, lists, tables, info/note/tip/warning panels, status labels, expand, code macro,
task lists and images as attachments.
"""
from __future__ import annotations

from html import escape

from ..model import (SOURCE_LABELS, BulletedList, Callout, Code, Divider, Heading, Image, Inline,
                     LinkToPage, NumberedList, Paragraph, Quote, SourceDocument, Table, TaskList,
                     Toggle, Unsupported)


def esc(text: str) -> str:
    return escape(text, quote=True)


def inline(parts: list[Inline]) -> str:
    out = []
    for part in parts:
        if part.status:
            out.append('<ac:structured-macro ac:name="status">'
                       f'<ac:parameter ac:name="colour">{part.status}</ac:parameter>'
                       f'<ac:parameter ac:name="title">{esc(part.text)}</ac:parameter>'
                       '</ac:structured-macro>')
            continue
        html = esc(part.text).replace("\n", "<br />")
        if not html:
            continue
        if part.code:
            html = f"<code>{html}</code>"
        if part.bold:
            html = f"<strong>{html}</strong>"
        if part.italic:
            html = f"<em>{html}</em>"
        if part.underline:
            html = f"<u>{html}</u>"
        if part.strike:
            html = f"<s>{html}</s>"
        if part.link:
            html = f'<a href="{esc(part.link)}">{html}</a>'
        out.append(html)
    return "".join(out)


def _macro(name: str, body: str, title: str | None = None) -> str:
    param = f'<ac:parameter ac:name="title">{esc(title)}</ac:parameter>' if title else ""
    return (f'<ac:structured-macro ac:name="{name}">{param}'
            f"<ac:rich-text-body>{body}</ac:rich-text-body></ac:structured-macro>")


class StorageFormatter:
    def __init__(self) -> None:
        self._task_id = 0

    def document(self, doc: SourceDocument, with_header: bool = True) -> str:
        self._task_id = 0
        body = self.blocks(doc.blocks)
        return (header(doc) if with_header else "") + body

    def blocks(self, blocks: list) -> str:
        return "".join(self.block(b) for b in blocks)

    def block(self, block) -> str:
        if isinstance(block, Heading):
            level = min(block.level + 1, 4)
            return f"<h{level}>{inline(block.text)}</h{level}>"
        if isinstance(block, Paragraph):
            return f"<p>{inline(block.text)}</p>"
        if isinstance(block, (BulletedList, NumberedList)):
            tag = "ul" if isinstance(block, BulletedList) else "ol"
            items = "".join(f"<li>{inline(i.text)}{self.blocks(i.children)}</li>" for i in block.items)
            return f"<{tag}>{items}</{tag}>"
        if isinstance(block, TaskList):
            tasks = []
            for item in block.items:
                self._task_id += 1
                status = "complete" if item.done else "incomplete"
                tasks.append(f"<ac:task><ac:task-id>{self._task_id}</ac:task-id>"
                             f"<ac:task-status>{status}</ac:task-status>"
                             f"<ac:task-body>{inline(item.text)}</ac:task-body></ac:task>")
                # Confluence task bodies only hold inline content: nested blocks follow the list
                if item.children:
                    tasks.append(f"</ac:task-list>{self.blocks(item.children)}<ac:task-list>")
            return f"<ac:task-list>{''.join(tasks)}</ac:task-list>".replace("<ac:task-list></ac:task-list>", "")
        if isinstance(block, Quote):
            return f"<blockquote>{self.blocks(block.children)}</blockquote>"
        if isinstance(block, Callout):
            return _macro(block.kind, self.blocks(block.children) or "<p></p>", block.title)
        if isinstance(block, Code):
            lang = (f'<ac:parameter ac:name="language">{esc(block.language)}</ac:parameter>'
                    if block.language else "")
            code = block.code.replace("]]>", "]]]]><![CDATA[>")
            return (f'<ac:structured-macro ac:name="code">{lang}'
                    f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>")
        if isinstance(block, Table):
            rows = []
            for index, row in enumerate(block.rows):
                cell_tag = "th" if block.header_row and index == 0 else "td"
                cells = "".join(f"<{cell_tag}>{self.blocks(c.children)}</{cell_tag}>" for c in row)
                rows.append(f"<tr>{cells}</tr>")
            return f"<table><tbody>{''.join(rows)}</tbody></table>"
        if isinstance(block, Divider):
            return "<hr />"
        if isinstance(block, Toggle):
            return _macro("expand", self.blocks(block.children) or "<p></p>", block.title or "Details")
        if isinstance(block, Image):
            width = f' ac:width="{block.width}"' if block.width else ""
            alt = f' ac:alt="{esc(block.alt)}"' if block.alt else ""
            image = (f"<ac:image{alt}{width}><ri:attachment ri:filename=\"{block.filename}\" />"
                     "</ac:image>")
            caption = f"<p><em>{inline(block.caption)}</em></p>" if block.caption else ""
            return f"<p>{image}</p>{caption}"
        if isinstance(block, LinkToPage):
            if block.url:
                return f'<p><a href="{esc(block.url)}">{esc(block.title)}</a></p>'
            return f"<p>{esc(block.title)}</p>"
        if isinstance(block, Unsupported):
            return _macro("note", f"<p>{esc(block.note)}</p>", "Nicht übertragen")
        raise TypeError(f"unknown block type: {type(block).__name__}")


def header(doc: SourceDocument) -> str:
    """Small info panel on top of every generated page."""
    label = SOURCE_LABELS.get(doc.source, doc.source)
    source = (f'<a href="{esc(doc.source_url)}">{esc(label)}</a>' if doc.source_url else esc(label))
    stand = f" · Stand: {doc.source_edited_at:%d.%m.%Y %H:%M}" if doc.source_edited_at else ""
    body = (f"<p>Erstellt mit ConfluenceSync aus {source}{stand} · "
            "Änderungen bitte in der Quelle vornehmen.</p>")
    return _macro("info", body)


def to_storage(doc: SourceDocument, with_header: bool = True) -> str:
    return StorageFormatter().document(doc, with_header)
