"""Common interface of all source connectors."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from ..model import Image, SourceDocument

NodeKind = Literal["notebook", "section_group", "section", "page", "workspace"]


class SourceNode(BaseModel):
    id: str
    title: str
    kind: NodeKind
    has_children: bool = False
    edited_at: datetime | None = None
    url: str | None = None


class PageInfo(BaseModel):
    title: str
    edited_at: datetime | None = None
    url: str | None = None


class SourceError(Exception):
    """Error with a message that can be shown to the user (German)."""


class Connector(Protocol):
    source: str

    def children(self, parent_id: str | None) -> list[SourceNode]: ...

    def search(self, query: str) -> list[SourceNode]: ...

    def load(self, page_id: str) -> SourceDocument: ...

    def page_info(self, page_id: str) -> PageInfo | None: ...

    def download_image(self, image: Image) -> bytes: ...


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
