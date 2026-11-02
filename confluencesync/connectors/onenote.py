"""OneNote connector (Microsoft Graph, delegated permission Notes.Read)."""
from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests

from ..model import Image, SourceDocument
from .base import PageInfo, SourceError, SourceNode, parse_time
from .onenote_html import parse_onenote_html

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_HOST = "graph.microsoft.com"


class OneNoteConnector:
    source = "onenote"

    def __init__(self, token_provider: Callable[[], str | None], session: requests.Session | None = None,
                 timeout: int = 30):
        self.token_provider = token_provider
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    # ---- HTTP --------------------------------------------------------------

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        if urlparse(url).hostname != GRAPH_HOST:
            raise SourceError("Unerwartete Adresse für Microsoft Graph.")
        token = self.token_provider()
        if not token:
            raise SourceError("Bitte zuerst unter «Verbindungen» mit Microsoft anmelden.")
        for attempt in range(4):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout,
                                        headers={"Authorization": f"Bearer {token}"})
            except requests.RequestException as exc:
                raise SourceError(f"Microsoft Graph ist nicht erreichbar ({type(exc).__name__}).") from None
            if resp.status_code in (429, 503, 504) and attempt < 3:
                time.sleep(min(float(resp.headers.get("Retry-After", 2 ** attempt)), 10))
                continue
            break
        if resp.status_code == 401:
            raise SourceError("Die Microsoft-Anmeldung ist abgelaufen. Bitte erneut anmelden.")
        if resp.status_code == 403:
            raise SourceError("Kein Zugriff auf OneNote. Fehlt die Berechtigung Notes.Read?")
        if resp.status_code == 404:
            raise SourceError("Nicht gefunden (gelöscht oder verschoben?).")
        if resp.status_code >= 400:
            raise SourceError(f"OneNote meldet einen Fehler (HTTP {resp.status_code}).")
        return resp

    def _json(self, path_or_url: str, params: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("https://") else GRAPH + path_or_url
        return self._request(url, params).json()

    def _all(self, path: str, params: dict | None = None, limit: int = 1000) -> list[dict]:
        data = self._json(path, params)
        items = list(data.get("value", []))
        while data.get("@odata.nextLink") and len(items) < limit:
            data = self._json(data["@odata.nextLink"])
            items += data.get("value", [])
        return items

    # ---- navigation --------------------------------------------------------

    def children(self, parent_id: str | None) -> list[SourceNode]:
        if not parent_id:
            notebooks = self._all("/me/onenote/notebooks", {"$select": "id,displayName,lastModifiedDateTime",
                                                            "$orderby": "displayName"})
            return [SourceNode(id=f"notebook:{n['id']}", title=n.get("displayName", "Notizbuch"),
                               kind="notebook", has_children=True) for n in notebooks]
        kind, _, raw = parent_id.partition(":")
        if kind in ("notebook", "group"):
            base = "/me/onenote/notebooks/" if kind == "notebook" else "/me/onenote/sectionGroups/"
            groups = self._all(base + raw + "/sectionGroups", {"$select": "id,displayName"})
            sections = self._all(base + raw + "/sections", {"$select": "id,displayName"})
            return ([SourceNode(id=f"group:{g['id']}", title=g.get("displayName", "Abschnittsgruppe"),
                                kind="section_group", has_children=True) for g in groups]
                    + [SourceNode(id=f"section:{s['id']}", title=s.get("displayName", "Abschnitt"),
                                  kind="section", has_children=True) for s in sections])
        if kind == "section":
            pages = self._all(f"/me/onenote/sections/{raw}/pages",
                              {"$select": "id,title,lastModifiedDateTime,order,level,links", "$top": 100})
            pages.sort(key=lambda p: p.get("order", 0))
            return [SourceNode(id=p["id"], title=p.get("title") or "(ohne Titel)", kind="page",
                               edited_at=parse_time(p.get("lastModifiedDateTime")),
                               url=((p.get("links") or {}).get("oneNoteWebUrl") or {}).get("href"))
                    for p in pages]
        return []

    def search(self, query: str) -> list[SourceNode]:
        return []

    # ---- pages -------------------------------------------------------------

    def _meta(self, page_id: str) -> dict:
        return self._json(f"/me/onenote/pages/{page_id}",
                          {"$select": "id,title,lastModifiedDateTime,links"})

    def page_info(self, page_id: str) -> PageInfo | None:
        try:
            meta = self._meta(page_id)
        except SourceError as exc:
            if "Nicht gefunden" in str(exc):
                return None
            raise
        return PageInfo(title=meta.get("title") or "(ohne Titel)",
                        edited_at=parse_time(meta.get("lastModifiedDateTime")),
                        url=((meta.get("links") or {}).get("oneNoteWebUrl") or {}).get("href"))

    def load(self, page_id: str) -> SourceDocument:
        meta = self._meta(page_id)
        html = self._request(f"{GRAPH}/me/onenote/pages/{page_id}/content").text
        title, blocks = parse_onenote_html(html)
        return SourceDocument(
            source="onenote", source_id=page_id, title=meta.get("title") or title or "(ohne Titel)",
            source_url=((meta.get("links") or {}).get("oneNoteWebUrl") or {}).get("href"),
            source_edited_at=parse_time(meta.get("lastModifiedDateTime")), blocks=blocks)

    def download_image(self, image: Image) -> bytes:
        return self._request(image.ref).content
