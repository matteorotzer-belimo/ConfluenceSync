"""OneNote page HTML (Microsoft Graph) -> content model.

Graph returns OneNote pages as HTML: absolutely positioned <div> containers holding paragraphs,
lists, tables and images. Containers are read top to bottom (then left to right); the free-form
layout itself is lost.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from ..model import (BulletedList, Code, Heading, Image, Inline, ListItem, NumberedList, Paragraph,
                     Table, TableCell, TaskItem, TaskList, Unsupported)

HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 3, "h5": 3, "h6": 3}
TAG_LABELS = {
    "important": ("Red", "WICHTIG"),
    "critical": ("Red", "KRITISCH"),
    "question": ("Yellow", "FRAGE"),
    "idea": ("Blue", "IDEE"),
    "remember-for-later": ("Grey", "MERKEN"),
    "definition": ("Grey", "DEFINITION"),
    "project-a": ("Blue", "PROJEKT A"),
    "project-b": ("Blue", "PROJEKT B"),
    "discuss-with-person-a": ("Yellow", "BESPRECHEN"),
    "discuss-with-person-b": ("Yellow", "BESPRECHEN"),
    "discuss-with-manager": ("Yellow", "BESPRECHEN"),
    "send-in-email": ("Grey", "PER MAIL"),
    "schedule-meeting": ("Grey", "TERMIN"),
    "call-back": ("Grey", "RÜCKRUF"),
    "client-request": ("Yellow", "KUNDENWUNSCH"),
}
INLINE_TAGS = {"span", "b", "strong", "i", "em", "u", "s", "strike", "del", "a", "code", "sup", "sub",
               "font", "cite", "br", "mark", "small", "big"}
BLOCK_TAGS = {"p", "div", "ul", "ol", "table", "img", "object", "iframe", "pre", "h1", "h2", "h3",
              "h4", "h5", "h6", "blockquote"}
MONO_FONTS = ("consolas", "courier", "monospace", "lucida console")
_PX = re.compile(r"(left|top)\s*:\s*(-?\d+(?:\.\d+)?)px")


def _style(tag: Tag) -> str:
    return (tag.get("style") or "").lower()


def _data_tags(tag: Tag) -> list[str]:
    return [t.strip().lower() for t in (tag.get("data-tag") or "").split(",") if t.strip()]


def _position(tag: Tag) -> tuple[float, float]:
    found = dict((k, float(v)) for k, v in _PX.findall(_style(tag)))
    return found.get("top", 0.0), found.get("left", 0.0)


# --------------------------------------------------------------------------- inline


def _format_of(tag: Tag, fmt: dict) -> dict:
    fmt = dict(fmt)
    name = tag.name
    style = _style(tag)
    if name in ("b", "strong") or re.search(r"font-weight\s*:\s*(bold|[6-9]00)", style):
        fmt["bold"] = True
    if name in ("i", "em", "cite") or "font-style:italic" in style.replace(" ", ""):
        fmt["italic"] = True
    if name == "u" or "underline" in style:
        fmt["underline"] = True
    if name in ("s", "strike", "del") or "line-through" in style:
        fmt["strike"] = True
    if name == "code" or any(f in style for f in MONO_FONTS):
        fmt["code"] = True
    if name == "a" and tag.get("href"):
        fmt["link"] = tag["href"]
    return fmt


def _inlines(el: Tag, fmt: dict, images: list[Tag]) -> list[Inline]:
    out: list[Inline] = []
    for child in el.children:
        if isinstance(child, NavigableString):
            if child.__class__.__name__ in ("Comment", "Doctype", "Declaration"):
                continue
            text = re.sub(r"[ \t\r\n\f]+", " ", str(child))
            if text:
                out.append(Inline(text=text, **fmt))
        elif isinstance(child, Tag):
            if child.name == "br":
                out.append(Inline(text="\n", **{k: v for k, v in fmt.items() if k == "link"}))
            elif child.name == "img":
                images.append(child)
            elif child.name in ("object", "iframe"):
                images.append(child)
            else:
                out.extend(_inlines(child, _format_of(child, fmt), images))
    return out


def _clean(parts: list[Inline]) -> list[Inline]:
    """Merge runs with equal formatting and trim surrounding whitespace."""
    merged: list[Inline] = []
    for part in parts:
        if merged and merged[-1].model_dump(exclude={"text"}) == part.model_dump(exclude={"text"}):
            merged[-1] = merged[-1].model_copy(update={"text": merged[-1].text + part.text})
        else:
            merged.append(part)
    while merged and not merged[0].text.strip() and not merged[0].status:
        merged.pop(0)
    while merged and not merged[-1].text.strip() and not merged[-1].status:
        merged.pop()
    if merged:
        merged[0] = merged[0].model_copy(update={"text": merged[0].text.lstrip(" ")})
        merged[-1] = merged[-1].model_copy(update={"text": merged[-1].text.rstrip(" ")})
    return [m for m in merged if m.text or m.status]


def _labels(tags: list[str]) -> list[Inline]:
    out = []
    for tag in tags:
        if tag in TAG_LABELS:
            colour, title = TAG_LABELS[tag]
            out += [Inline(text=title, status=colour), Inline(text=" ")]
    return out


# --------------------------------------------------------------------------- blocks


class _Builder:
    def __init__(self) -> None:
        self.blocks: list = []
        self.pending: list[Inline] = []

    def flush(self) -> None:
        text = _clean(self.pending)
        self.pending = []
        if text:
            self.blocks.append(Paragraph(text=text))

    def add(self, block) -> None:
        self.flush()
        if isinstance(block, TaskList) and self.blocks and isinstance(self.blocks[-1], TaskList):
            self.blocks[-1].items.extend(block.items)
        else:
            self.blocks.append(block)


def _image(tag: Tag) -> Image | None:
    src = tag.get("data-fullres-src") or tag.get("src")
    if not src:
        return None
    mime = tag.get("data-fullres-src-type") or tag.get("data-src-type") or "image/png"
    width = None
    try:
        width = min(int(float(tag.get("width"))), 1200) if tag.get("width") else None
    except ValueError:
        width = None
    return Image(ref=src, mime=mime, alt=tag.get("alt") or None, width=width)


def _embedded(tag: Tag) -> list:
    if tag.name == "img":
        image = _image(tag)
        return [image] if image else []
    if tag.name == "object":
        name = tag.get("data-attachment") or "Datei"
        return [Unsupported(source_type="onenote:attachment",
                            note=f"Dateianhang «{name}» wurde nicht übertragen. Bitte in OneNote öffnen.")]
    return [Unsupported(source_type="onenote:embed",
                        note="Eingebetteter Inhalt (z. B. Video) wurde nicht übertragen.")]


def _paragraph(tag: Tag, builder: _Builder) -> None:
    tags = _data_tags(tag)
    embedded: list[Tag] = []
    text = _clean(_inlines(tag, _format_of(tag, {}), embedded))
    is_todo = any(t.startswith("to-do") for t in tags)
    if is_todo:
        done = any(t.endswith(":completed") for t in tags if t.startswith("to-do"))
        builder.add(TaskList(items=[TaskItem(done=done, text=_labels(tags) + text)]))
    elif text:
        builder.add(Paragraph(text=_labels(tags) + text))
    for item in embedded:
        for block in _embedded(item):
            builder.add(block)


def _list(tag: Tag) -> BulletedList | NumberedList:
    items: list[ListItem] = []
    for child in tag.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "li":
            items.append(_list_item(child))
        elif child.name in ("ul", "ol"):
            nested = _list(child)
            if items:
                items[-1].children.append(nested)
            else:
                items.append(ListItem(children=[nested]))
    cls = NumberedList if tag.name == "ol" else BulletedList
    return cls(items=items)


def _list_item(li: Tag) -> ListItem:
    tags = _data_tags(li)
    inline_parts: list[Inline] = []
    embedded: list[Tag] = []
    children: list = []
    first_paragraph_used = False
    for child in li.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol"):
            children.append(_list(child))
        elif isinstance(child, Tag) and child.name == "p" and (first_paragraph_used or inline_parts):
            sub = _Builder()
            _paragraph(child, sub)
            sub.flush()
            children.extend(sub.blocks)
        elif isinstance(child, Tag) and child.name == "p":
            first_paragraph_used = True
            inline_parts.extend(_inlines(child, _format_of(child, {}), embedded))
            tags += _data_tags(child)
        elif isinstance(child, Tag) and child.name in ("table", "pre", "div"):
            children.extend(convert(child))
        elif isinstance(child, Tag):
            if child.name in ("img", "object", "iframe"):
                embedded.append(child)
                continue
            inline_parts.extend(_inlines(child, _format_of(child, {}), embedded))
        elif isinstance(child, NavigableString) and child.__class__.__name__ == "NavigableString":
            inline_parts.extend(_inlines_from_string(child))
    text = _clean(inline_parts)
    todo = [t for t in tags if t.startswith("to-do")]
    if todo:
        mark = "☑ " if any(t.endswith(":completed") for t in todo) else "☐ "
        text = [Inline(text=mark)] + text
    text = _labels([t for t in tags if not t.startswith("to-do")]) + text
    for item in embedded:
        children.extend(_embedded(item))
    return ListItem(text=text, children=children)


def _inlines_from_string(text: NavigableString) -> list[Inline]:
    cleaned = re.sub(r"[ \t\r\n\f]+", " ", str(text))
    return [Inline(text=cleaned)] if cleaned else []


def _table(tag: Tag) -> Table:
    rows: list[list[TableCell]] = []
    header = False
    for index, tr in enumerate(tag.find_all("tr")):
        if tr.find_parent("table") is not tag:
            continue
        cells = [c for c in tr.children if isinstance(c, Tag) and c.name in ("td", "th")]
        if index == 0 and cells and all(c.name == "th" for c in cells):
            header = True
        rows.append([TableCell(children=convert(c)) for c in cells])
    return Table(header_row=header, rows=[r for r in rows if r])


def convert(el: Tag) -> list:
    """Convert the children of an element into blocks."""
    builder = _Builder()
    for child in el.children:
        if isinstance(child, NavigableString):
            if child.__class__.__name__ in ("Comment", "Doctype", "Declaration"):
                continue
            builder.pending.extend(_inlines_from_string(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in HEADING_LEVEL:
            embedded: list[Tag] = []
            text = _clean(_inlines(child, {}, embedded))
            if text:
                builder.add(Heading(level=HEADING_LEVEL[name], text=text))
            for item in embedded:
                for block in _embedded(item):
                    builder.add(block)
        elif name == "p":
            _paragraph(child, builder)
        elif name in ("ul", "ol"):
            builder.add(_list(child))
        elif name == "table":
            builder.add(_table(child))
        elif name in ("img", "object", "iframe"):
            for block in _embedded(child):
                builder.add(block)
        elif name == "pre":
            builder.add(Code(code=child.get_text()))
        elif name == "br":
            builder.pending.append(Inline(text="\n"))
        elif name in ("div", "blockquote", "section", "article") or name not in INLINE_TAGS:
            builder.flush()
            for block in convert(child):
                builder.add(block)
        else:
            embedded = []
            builder.pending.extend(_inlines(child, _format_of(child, {}), embedded))
            for item in embedded:
                for block in _embedded(item):
                    builder.add(block)
    builder.flush()
    return builder.blocks


def parse_onenote_html(html: str) -> tuple[str, list]:
    """Return (title, blocks) of a OneNote page."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    body = soup.body or soup
    containers = [c for c in body.children if isinstance(c, Tag)]
    if containers and any("position:absolute" in _style(c).replace(" ", "") for c in containers):
        loose = [c for c in body.children if not isinstance(c, Tag) and str(c).strip()]
        ordered = sorted(containers, key=_position)
        wrapper = BeautifulSoup("<div></div>", "html.parser").div
        for text in loose:
            wrapper.append(NavigableString(str(text)))
        for container in ordered:
            wrapper.append(container.extract())
        body = wrapper
    return title, convert(body)
