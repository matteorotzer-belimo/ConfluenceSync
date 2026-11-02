"""Source-independent content model: a tree of blocks with inline formatting.

Every connector (OneNote, Notion, ...) produces a `SourceDocument`; everything after that
(formatter, preview, sync) only works with this model.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

StatusColour = Literal["Grey", "Red", "Yellow", "Green", "Blue"]
CalloutKind = Literal["info", "note", "tip", "warning"]


class Inline(BaseModel):
    """A run of text with formatting. With `status` set, the text is shown as a status label."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    code: bool = False
    link: str | None = None
    status: StatusColour | None = None


class ListItem(BaseModel):
    text: list[Inline] = Field(default_factory=list)
    children: list["Block"] = Field(default_factory=list)


class TaskItem(BaseModel):
    done: bool = False
    text: list[Inline] = Field(default_factory=list)
    children: list["Block"] = Field(default_factory=list)


class Heading(BaseModel):
    type: Literal["heading"] = "heading"
    level: int = Field(1, ge=1, le=3)
    text: list[Inline]


class Paragraph(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: list[Inline]


class BulletedList(BaseModel):
    type: Literal["bulleted_list"] = "bulleted_list"
    items: list[ListItem]


class NumberedList(BaseModel):
    type: Literal["numbered_list"] = "numbered_list"
    items: list[ListItem]


class TaskList(BaseModel):
    type: Literal["task_list"] = "task_list"
    items: list[TaskItem]


class Quote(BaseModel):
    type: Literal["quote"] = "quote"
    children: list["Block"]


class Callout(BaseModel):
    type: Literal["callout"] = "callout"
    kind: CalloutKind = "info"
    title: str | None = None
    children: list["Block"]


class Code(BaseModel):
    type: Literal["code"] = "code"
    language: str | None = None
    code: str


class TableCell(BaseModel):
    children: list["Block"] = Field(default_factory=list)


class Table(BaseModel):
    type: Literal["table"] = "table"
    header_row: bool = False
    rows: list[list[TableCell]]


class Divider(BaseModel):
    type: Literal["divider"] = "divider"


class Toggle(BaseModel):
    type: Literal["toggle"] = "toggle"
    title: str
    children: list["Block"]


class Image(BaseModel):
    """An image. `ref` is a stable source reference (used for the attachment name and change
    detection); `download_url` is only needed when the URL is short-lived (Notion)."""

    type: Literal["image"] = "image"
    ref: str
    mime: str = "image/png"
    alt: str | None = None
    caption: list[Inline] = Field(default_factory=list)
    width: int | None = None
    download_url: str | None = Field(None, exclude=True)

    @property
    def filename(self) -> str:
        """Stable attachment file name, derived from the source reference."""
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/gif": "gif",
               "image/webp": "webp", "image/svg+xml": "svg", "image/bmp": "bmp"}.get(self.mime.lower(), "png")
        return f"cs-{hashlib.sha1(self.ref.encode('utf-8')).hexdigest()[:12]}.{ext}"


class LinkToPage(BaseModel):
    type: Literal["link_to_page"] = "link_to_page"
    title: str
    url: str | None = None


class Unsupported(BaseModel):
    """Content that cannot be transferred. Shown as a visible note, never dropped silently."""

    type: Literal["unsupported"] = "unsupported"
    source_type: str
    note: str


Block = Annotated[
    Union[Heading, Paragraph, BulletedList, NumberedList, TaskList, Quote, Callout, Code, Table,
          Divider, Toggle, Image, LinkToPage, Unsupported],
    Field(discriminator="type"),
]

for _model in (ListItem, TaskItem, Quote, Callout, TableCell, Toggle):
    _model.model_rebuild()


SourceKind = Literal["onenote", "notion", "demo"]
SOURCE_LABELS = {"onenote": "OneNote", "notion": "Notion", "demo": "Beispielnotizen"}


class SourceDocument(BaseModel):
    source: SourceKind
    source_id: str
    source_url: str | None = None
    title: str
    source_edited_at: datetime | None = None
    blocks: list[Block] = Field(default_factory=list)

    def content_hash(self) -> str:
        """Hash of title and content: changes only if the note itself changed."""
        payload = json.dumps({"title": self.title,
                              "blocks": [b.model_dump(mode="json") for b in self.blocks]},
                             sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def walk(blocks: list) -> "list":
    """All blocks of a tree in document order (depth first)."""
    out = []
    for block in blocks:
        out.append(block)
        for child_list in _child_lists(block):
            out.extend(walk(child_list))
    return out


def _child_lists(block) -> list[list]:
    if isinstance(block, (BulletedList, NumberedList, TaskList)):
        return [item.children for item in block.items]
    if isinstance(block, (Quote, Callout, Toggle)):
        return [block.children]
    if isinstance(block, Table):
        return [cell.children for row in block.rows for cell in row]
    return []


def images(doc: SourceDocument) -> list[Image]:
    seen: dict[str, Image] = {}
    for block in walk(doc.blocks):
        if isinstance(block, Image) and block.filename not in seen:
            seen[block.filename] = block
    return list(seen.values())


def unsupported(doc: SourceDocument) -> list[Unsupported]:
    return [b for b in walk(doc.blocks) if isinstance(b, Unsupported)]


def plain(text: list[Inline]) -> str:
    return "".join(part.text for part in text)
