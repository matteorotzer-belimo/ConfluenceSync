"""Small client for the Confluence Data Center REST API (/rest/api/content).

Adapted from belimo_ticket-analytics scripts/confluence_sync.py. Authentication with a personal
access token (Bearer). The token is only sent in the Authorization header and never logged or
included in error messages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .checks import norm


class ConfluenceError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class Page:
    id: str
    title: str
    version: int
    parent_id: str | None = None
    space_key: str | None = None
    body: str | None = None
    url: str | None = None


def friendly_message(exc: Exception) -> str:
    """German message for the UI."""
    if isinstance(exc, ConfluenceError):
        status = exc.status
        if status == 401:
            return "Confluence lehnt den Zugriffstoken ab. Ist er abgelaufen oder falsch kopiert?"
        if status == 403:
            return "Dafür fehlt dir in Confluence die Berechtigung (z. B. kein Schreibrecht im Space)."
        if status == 404:
            return "Die Seite oder der Space wurde in Confluence nicht gefunden (gelöscht oder keine Leserechte)."
        if status == 409:
            return "Die Seite wurde gerade in Confluence geändert. Bitte die Vorschau neu laden."
        if status == 400 and "title" in str(exc).lower():
            return "In diesem Space gibt es schon eine Seite mit diesem Titel. Bitte einen anderen Titel wählen."
        return f"Confluence meldet einen Fehler: {exc}"
    return str(exc)


class ConfluenceClient:
    def __init__(self, base_url: str, token: str, session: requests.Session | None = None,
                 timeout: int = 30):
        base = base_url.strip().rstrip("/")
        for suffix in ("/rest/api", "/rest"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        if not re.match(r"^https?://", base):
            raise ConfluenceError("Die Confluence-Adresse muss mit https:// beginnen.")
        self.base = base
        self.api = base + "/rest/api"
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    # ---- low level ---------------------------------------------------------

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self.session.request(method, self.api + path, timeout=self.timeout, **kwargs)
        except requests.exceptions.SSLError:
            raise ConfluenceError("Sichere Verbindung zu Confluence fehlgeschlagen (Zertifikat).") from None
        except requests.RequestException as exc:
            raise ConfluenceError(
                f"Confluence ist nicht erreichbar ({type(exc).__name__}). Stimmt die Adresse, "
                "und bist du im Firmennetz bzw. mit VPN verbunden?") from None
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", "")
            except ValueError:
                detail = ""
            raise ConfluenceError(f"{method} {path} -> HTTP {resp.status_code} {detail}".strip(),
                                  resp.status_code)
        if "html" in resp.headers.get("Content-Type", "") and resp.status_code == 200:
            # login pages of SSO proxies answer with HTML instead of JSON
            raise ConfluenceError("Confluence hat keine API-Antwort geliefert. Stimmt die Adresse?")
        return resp.json() if resp.content else {}

    def _page(self, data: dict, parent_id: str | None = None) -> Page:
        ancestors = data.get("ancestors") or []
        if parent_id is None and ancestors:
            parent_id = str(ancestors[-1]["id"])
        body = ((data.get("body") or {}).get("storage") or {}).get("value")
        webui = (data.get("_links") or {}).get("webui")
        return Page(str(data["id"]), data["title"], int((data.get("version") or {}).get("number", 1)),
                    parent_id, (data.get("space") or {}).get("key"),
                    norm(body) if body is not None else None,
                    self.base + webui if webui else f"{self.base}/pages/viewpage.action?pageId={data['id']}")

    # ---- account and navigation -------------------------------------------

    def current_user(self) -> dict:
        data = self._call("GET", "/user/current")
        if data.get("type") == "anonymous" or not data.get("username") and not data.get("userKey"):
            raise ConfluenceError("Confluence hat dich nicht erkannt. Ist der Token korrekt?", 401)
        return {"name": data.get("displayName") or data.get("username"), "username": data.get("username")}

    def spaces(self, max_items: int = 1000) -> list[dict]:
        """Global spaces visible to the user, plus the personal space."""
        result, start = [], 0
        while len(result) < max_items:
            data = self._call("GET", "/space", params={"type": "global", "limit": 200, "start": start})
            batch = data.get("results", [])
            result += [{"key": s["key"], "name": s.get("name", s["key"]), "personal": False} for s in batch]
            if not batch or "next" not in data.get("_links", {}):
                break
            start += len(batch)
        try:
            user = self.current_user()
            if user.get("username"):
                personal = self._call("GET", f"/space/~{user['username']}")
                result.insert(0, {"key": personal["key"], "name": personal.get("name", personal["key"]),
                                  "personal": True})
        except ConfluenceError:
            pass
        return result

    def search_pages(self, space: str, query: str = "", limit: int = 25) -> list[dict]:
        cleaned = re.sub(r'[+\-&|!(){}\[\]^~*?:\\"/]', " ", query).strip()
        space_q = space.replace("\\", "").replace('"', "")
        cql = f'space = "{space_q}" and type = page'
        if cleaned:
            cql += f' and title ~ "{cleaned}*"'
        cql += " order by lastmodified desc"
        data = self._call("GET", "/content/search",
                          params={"cql": cql, "limit": limit, "expand": "ancestors"})
        pages = []
        for item in data.get("results", []):
            path = " / ".join(a.get("title", "") for a in (item.get("ancestors") or [])[-2:])
            pages.append({"id": str(item["id"]), "title": item["title"], "path": path})
        return pages

    # ---- pages -------------------------------------------------------------

    def get_page(self, page_id: str, body: bool = False) -> Page:
        expand = "version,ancestors,space" + (",body.storage" if body else "")
        return self._page(self._call("GET", f"/content/{page_id}", params={"expand": expand}))

    def find_title(self, space: str, title: str) -> list[Page]:
        data = self._call("GET", "/content", params={"spaceKey": space, "title": title, "type": "page",
                                                     "expand": "version,ancestors,space"})
        return [self._page(r) for r in data.get("results", [])]

    def create_page(self, space: str, parent_id: str | None, title: str, body: str) -> Page:
        payload: dict = {"type": "page", "title": title, "space": {"key": space},
                         "body": {"storage": {"value": body, "representation": "storage"}}}
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]
        return self._page(self._call("POST", "/content", json=payload), parent_id=parent_id)

    def update_page(self, page: Page, title: str, body: str) -> Page:
        """New version of an existing page. Fails with HTTP 409 if someone saved in between."""
        payload = {"id": page.id, "type": "page", "title": title,
                   "space": {"key": page.space_key}, "version": {"number": page.version + 1},
                   "body": {"storage": {"value": body, "representation": "storage"}}}
        return self._page(self._call("PUT", f"/content/{page.id}", json=payload), parent_id=page.parent_id)

    # ---- attachments -------------------------------------------------------

    def attachment_names(self, page_id: str) -> set[str]:
        names, start = set(), 0
        while True:
            data = self._call("GET", f"/content/{page_id}/child/attachment",
                              params={"limit": 200, "start": start})
            batch = data.get("results", [])
            names |= {a["title"] for a in batch}
            if not batch or "next" not in data.get("_links", {}):
                return names
            start += len(batch)

    def upload_attachment(self, page_id: str, filename: str, data: bytes, mime: str) -> None:
        self._call("POST", f"/content/{page_id}/child/attachment",
                   headers={"X-Atlassian-Token": "no-check"},
                   files={"file": (filename, data, mime)},
                   data={"minorEdit": "true", "comment": "ConfluenceSync"})
