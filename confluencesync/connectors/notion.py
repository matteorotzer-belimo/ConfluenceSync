"""Notion connector (internal integration token, API version 2022-06-28)."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

from ..model import Image, SourceDocument
from .base import PageInfo, SourceError, SourceNode, parse_time
from .notion_blocks import convert

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_DEPTH = 8
NO_RECURSE = {"child_page", "child_database"}


def page_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title") or []) or "(ohne Titel)"
    return "(ohne Titel)"


class NotionConnector:
    source = "notion"

    def __init__(self, token: str, session: requests.Session | None = None, timeout: int = 30,
                 pause: float = 0.34):
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}",
                                     "Notion-Version": NOTION_VERSION})
        self.timeout = timeout
        self.pause = pause          # Notion allows about 3 requests per second

    def _call(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(4):
            try:
                resp = self.session.request(method, API + path, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                raise SourceError(f"Notion ist nicht erreichbar ({type(exc).__name__}).") from None
            if resp.status_code == 429 and attempt < 3:
                time.sleep(min(float(resp.headers.get("Retry-After", 1 + attempt)), 10))
                continue
            break
        if resp.status_code == 401:
            raise SourceError("Notion lehnt den Token ab. Ist er korrekt kopiert?")
        if resp.status_code in (403, 404):
            raise SourceError("Nicht gefunden. Ist die Seite mit der ConfluenceSync-Integration geteilt?")
        if resp.status_code >= 400:
            raise SourceError(f"Notion meldet einen Fehler (HTTP {resp.status_code}).")
        if self.pause:
            time.sleep(self.pause)
        return resp.json()

    def me(self) -> dict:
        data = self._call("GET", "/users/me")
        bot = data.get("bot") or {}
        return {"name": data.get("name") or "Notion-Integration",
                "workspace": bot.get("workspace_name") or ""}

    def _search(self, query: str = "", limit: int = 200) -> list[SourceNode]:
        nodes, cursor = [], None
        while len(nodes) < limit:
            body: dict = {"filter": {"property": "object", "value": "page"}, "page_size": 100,
                          "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
            if query:
                body["query"] = query
            if cursor:
                body["start_cursor"] = cursor
            data = self._call("POST", "/search", json=body)
            for page in data.get("results", []):
                if page.get("archived") or page.get("in_trash"):
                    continue
                nodes.append(SourceNode(id=page["id"], title=page_title(page), kind="page",
                                        edited_at=parse_time(page.get("last_edited_time")),
                                        url=page.get("url")))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return nodes

    def children(self, parent_id: str | None) -> list[SourceNode]:
        return self._search() if not parent_id else []

    def search(self, query: str) -> list[SourceNode]:
        return self._search(query)

    def _blocks(self, block_id: str, depth: int = 0) -> list[dict]:
        blocks, cursor = [], None
        while True:
            params = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            data = self._call("GET", f"/blocks/{block_id}/children", params=params)
            blocks += data.get("results", [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        for block in blocks:
            if block.get("has_children") and block.get("type") not in NO_RECURSE and depth < MAX_DEPTH:
                block["children"] = self._blocks(block["id"], depth + 1)
        return blocks

    def page_info(self, page_id: str) -> PageInfo | None:
        try:
            page = self._call("GET", f"/pages/{page_id}")
        except SourceError as exc:
            if "Nicht gefunden" in str(exc):
                return None
            raise
        if page.get("archived") or page.get("in_trash"):
            return None
        return PageInfo(title=page_title(page), edited_at=parse_time(page.get("last_edited_time")),
                        url=page.get("url"))

    def load(self, page_id: str) -> SourceDocument:
        page = self._call("GET", f"/pages/{page_id}")
        return SourceDocument(source="notion", source_id=page_id, title=page_title(page),
                              source_url=page.get("url"),
                              source_edited_at=parse_time(page.get("last_edited_time")),
                              blocks=convert(self._blocks(page_id)))

    def download_image(self, image: Image) -> bytes:
        url = image.download_url or ""
        if urlparse(url).scheme != "https":
            raise SourceError("Bild-Adresse ist ungültig.")
        try:
            # file URLs are pre-signed: no Notion token is sent to the storage host
            resp = requests.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceError(f"Bild konnte nicht geladen werden ({type(exc).__name__}).") from None
        if resp.status_code >= 400:
            raise SourceError("Bild konnte nicht geladen werden (Link abgelaufen? Vorschau neu laden).")
        return resp.content
