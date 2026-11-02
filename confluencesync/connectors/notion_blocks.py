"""Notion blocks (API JSON) -> content model. Children must already be attached as "children"."""
from __future__ import annotations

import mimetypes
from urllib.parse import urlparse

from ..model import (BulletedList, Callout, Code, Divider, Heading, Image, Inline, LinkToPage,
                     ListItem, NumberedList, Paragraph, Quote, Table, TableCell, TaskItem, TaskList,
                     Toggle, Unsupported)

WARNING_EMOJI = {"⚠️", "⚠", "❗", "‼️", "🚨", "⛔", "❌", "🔥", "🛑"}
TIP_EMOJI = {"💡", "✅", "✔️", "👍", "🌱", "🚀"}
NOTE_EMOJI = {"📝", "📌", "✏️", "🗒️", "📒", "🔔", "👉"}
SKIPPED = {"table_of_contents", "breadcrumb"}
LANGUAGES = {"plain text": None, "shell": "bash", "c#": "csharp", "c++": "cpp", "markdown": None}


def page_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"


def rich_text(items: list[dict]) -> list[Inline]:
    out = []
    for item in items or []:
        ann = item.get("annotations") or {}
        text = item.get("plain_text")
        if text is None:
            text = (item.get("text") or {}).get("content", "")
        link = item.get("href") or ((item.get("text") or {}).get("link") or {}).get("url")
        if link and link.startswith("/"):
            link = "https://www.notion.so" + link
        out.append(Inline(text=text, bold=bool(ann.get("bold")), italic=bool(ann.get("italic")),
                          underline=bool(ann.get("underline")), strike=bool(ann.get("strikethrough")),
                          code=bool(ann.get("code")), link=link))
    return [i for i in out if i.text]


def _plain(items: list[dict]) -> str:
    return "".join(i.text for i in rich_text(items))


def _callout_kind(data: dict) -> str:
    emoji = ((data.get("icon") or {}).get("emoji")) or ""
    if emoji in WARNING_EMOJI:
        return "warning"
    if emoji in TIP_EMOJI:
        return "tip"
    if emoji in NOTE_EMOJI:
        return "note"
    colour = (data.get("color") or "").split("_")[0]
    return {"red": "warning", "orange": "warning", "yellow": "note", "green": "tip"}.get(colour, "info")


def _image(block: dict) -> Image:
    data = block["image"]
    url = (data.get("file") or data.get("external") or {}).get("url", "")
    mime = mimetypes.guess_type(urlparse(url).path)[0] or "image/png"
    caption = rich_text(data.get("caption") or [])
    return Image(ref=f"notion:{block['id']}", download_url=url, mime=mime,
                 alt="".join(c.text for c in caption) or None, caption=caption)


def _file_name(data: dict) -> str:
    name = data.get("name") or "".join(c.get("plain_text", "") for c in data.get("caption") or [])
    if not name:
        url = (data.get("file") or data.get("external") or {}).get("url", "")
        name = urlparse(url).path.rsplit("/", 1)[-1] or "Datei"
    return name


def convert(blocks: list[dict]) -> list:
    out: list = []
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype) or {}
        children = convert(block.get("children") or [])
        if btype in ("bulleted_list_item", "numbered_list_item"):
            cls = BulletedList if btype == "bulleted_list_item" else NumberedList
            item = ListItem(text=rich_text(data.get("rich_text")), children=children)
            if out and type(out[-1]) is cls:
                out[-1].items.append(item)
            else:
                out.append(cls(items=[item]))
        elif btype == "to_do":
            item = TaskItem(done=bool(data.get("checked")), text=rich_text(data.get("rich_text")),
                            children=children)
            if out and isinstance(out[-1], TaskList):
                out[-1].items.append(item)
            else:
                out.append(TaskList(items=[item]))
        else:
            out.extend(_single(block, btype, data, children))
    return out


def _single(block: dict, btype: str, data: dict, children: list) -> list:
    if btype == "paragraph":
        text = rich_text(data.get("rich_text"))
        return ([Paragraph(text=text)] if text else []) + children
    if btype in ("heading_1", "heading_2", "heading_3"):
        text = rich_text(data.get("rich_text"))
        if data.get("is_toggleable") and children:
            return [Heading(level=int(btype[-1]), text=text), *children]
        return [Heading(level=int(btype[-1]), text=text)] if text else []
    if btype == "toggle":
        return [Toggle(title=_plain(data.get("rich_text")) or "Details", children=children)]
    if btype == "quote":
        text = rich_text(data.get("rich_text"))
        return [Quote(children=([Paragraph(text=text)] if text else []) + children)]
    if btype == "callout":
        text = rich_text(data.get("rich_text"))
        return [Callout(kind=_callout_kind(data), children=([Paragraph(text=text)] if text else []) + children)]
    if btype == "code":
        language = (data.get("language") or "").lower()
        return [Code(language=LANGUAGES.get(language, language) or None, code=_plain(data.get("rich_text")))]
    if btype == "equation":
        return [Paragraph(text=[Inline(text=data.get("expression", ""), code=True)])]
    if btype == "divider":
        return [Divider()]
    if btype == "table":
        rows = []
        for row in block.get("children") or []:
            cells = (row.get("table_row") or {}).get("cells") or []
            rows.append([TableCell(children=[Paragraph(text=rich_text(c))] if rich_text(c) else [])
                         for c in cells])
        return [Table(header_row=bool(data.get("has_column_header")), rows=rows)] if rows else []
    if btype == "image":
        return [_image(block)]
    if btype == "child_page":
        return [LinkToPage(title=data.get("title") or "Unterseite", url=page_url(block["id"]))]
    if btype == "link_to_page":
        target = data.get("page_id") or data.get("database_id")
        return [LinkToPage(title="Verknüpfte Notion-Seite", url=page_url(target) if target else None)]
    if btype in ("bookmark", "link_preview"):
        url = data.get("url", "")
        caption = rich_text(data.get("caption") or [])
        label = "".join(c.text for c in caption) or url
        return [Paragraph(text=[Inline(text=label, link=url)])] if url else []
    if btype in ("column_list", "column", "synced_block", "template"):
        if children:
            return children
        if btype == "synced_block":
            return [Unsupported(source_type="notion:synced_block",
                                note="Synchronisierter Block ohne Zugriff auf das Original wurde nicht übertragen.")]
        return []
    if btype == "child_database":
        return [Unsupported(source_type="notion:child_database",
                            note=f"Datenbank «{data.get('title') or 'ohne Titel'}» kann nicht übertragen werden.")]
    if btype in ("file", "pdf", "video", "audio"):
        return [Unsupported(source_type=f"notion:{btype}",
                            note=f"Datei «{_file_name(data)}» wurde nicht übertragen. Bitte in Notion öffnen.")]
    if btype == "embed":
        return [Unsupported(source_type="notion:embed",
                            note=f"Eingebetteter Inhalt ({data.get('url', '')}) wurde nicht übertragen.")]
    if btype in SKIPPED:
        return []
    return [Unsupported(source_type=f"notion:{btype or 'unknown'}",
                        note=f"Notion-Block «{btype or 'unbekannt'}» wird nicht unterstützt.")]
