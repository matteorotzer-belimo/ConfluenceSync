from __future__ import annotations

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from confluencesync.confluence.client import ConfluenceClient, ConfluenceError, Page, friendly_message

BASE = "https://confluence.example.com"
TOKEN = "pat-SyntheticToken-123456"


class FakeResponse:
    def __init__(self, status: int = 200, data=None, content_type: str = "application/json", raw: bytes | None = None):
        self.status_code = status
        self._data = data
        self.headers = {"Content-Type": content_type}
        if raw is not None:
            self.content = raw
        else:
            self.content = b"" if data is None else b"{...}"

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeSession:
    def __init__(self, *responses):
        self.headers = CaseInsensitiveDict()
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def client(*responses, base=BASE) -> tuple[ConfluenceClient, FakeSession]:
    session = FakeSession(*responses)
    return ConfluenceClient(base, TOKEN, session=session), session


def page_json(page_id="42", version=3, body=None, ancestors=None):
    data = {"id": page_id, "title": "Seite", "version": {"number": version}, "space": {"key": "DOKU"},
            "ancestors": ancestors or [], "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"}}
    if body is not None:
        data["body"] = {"storage": {"value": body, "representation": "storage"}}
    return data


def test_bearer_token_header():
    c, session = client()
    assert session.headers["Authorization"] == f"Bearer {TOKEN}"
    assert session.headers["Accept"] == "application/json"
    assert c.timeout == 30


@pytest.mark.parametrize("url", [BASE, BASE + "/", f"  {BASE}/rest/api/ ", BASE + "/rest", BASE + "/rest/api"])
def test_url_normalisation(url):
    c, _ = client(base=url)
    assert c.base == BASE
    assert c.api == BASE + "/rest/api"


def test_url_with_context_path_and_invalid_url():
    c, _ = client(base="https://intranet.example.com/confluence/")
    assert c.api == "https://intranet.example.com/confluence/rest/api"
    with pytest.raises(ConfluenceError, match="https://"):
        ConfluenceClient("confluence.example.com", TOKEN, session=FakeSession())


def test_requests_go_to_api_with_timeout():
    c, session = client(FakeResponse(data={"username": "anna", "displayName": "Anna Muster"}))
    assert c.current_user() == {"name": "Anna Muster", "username": "anna"}
    call = session.calls[0]
    assert call["method"] == "GET" and call["url"] == BASE + "/rest/api/user/current"
    assert call["timeout"] == 30


def test_anonymous_user_is_rejected():
    c, _ = client(FakeResponse(data={"type": "anonymous"}))
    with pytest.raises(ConfluenceError) as info:
        c.current_user()
    assert info.value.status == 401


@pytest.mark.parametrize("status,expected", [
    (401, "Zugriffstoken ab"),
    (403, "Berechtigung"),
    (404, "nicht gefunden"),
    (409, "gerade in Confluence geändert"),
    (500, "Confluence meldet einen Fehler"),
])
def test_http_errors_are_mapped(status, expected):
    c, _ = client(FakeResponse(status, data={"message": "Detail vom Server"}))
    with pytest.raises(ConfluenceError) as info:
        c.get_page("42")
    exc = info.value
    assert exc.status == status
    assert f"HTTP {status}" in str(exc) and "Detail vom Server" in str(exc)
    assert expected in friendly_message(exc)
    assert TOKEN not in str(exc) and TOKEN not in friendly_message(exc)


def test_duplicate_title_error_message():
    exc = ConfluenceError("POST /content -> HTTP 400 A page with this title already exists", 400)
    assert "schon eine Seite mit diesem Titel" in friendly_message(exc)
    assert friendly_message(ValueError("anders")) == "anders"


def test_error_without_json_body():
    c, _ = client(FakeResponse(502, data=None, raw=b"<html>Bad gateway</html>"))
    with pytest.raises(ConfluenceError) as info:
        c.get_page("1")
    assert info.value.status == 502
    assert str(info.value) == "GET /content/1 -> HTTP 502"


def test_network_errors():
    c, _ = client(requests.ConnectionError("boom"), requests.exceptions.SSLError("cert"))
    with pytest.raises(ConfluenceError, match="nicht erreichbar") as info:
        c.get_page("1")
    assert info.value.status is None
    with pytest.raises(ConfluenceError, match="Zertifikat"):
        c.get_page("1")


def test_html_login_page_instead_of_json():
    c, _ = client(FakeResponse(200, data=None, content_type="text/html; charset=utf-8", raw=b"<html>login</html>"))
    with pytest.raises(ConfluenceError, match="keine API-Antwort"):
        c.current_user()


def test_get_page_parses_response():
    c, session = client(FakeResponse(data=page_json(body="<p>a</p>\r\n<p>b</p>",
                                                    ancestors=[{"id": 1}, {"id": 7}])))
    page = c.get_page("42", body=True)
    assert page == Page("42", "Seite", 3, "7", "DOKU", "<p>a</p>\n<p>b</p>",
                        BASE + "/pages/viewpage.action?pageId=42")
    assert session.calls[0]["params"] == {"expand": "version,ancestors,space,body.storage"}


def test_get_page_without_body():
    c, session = client(FakeResponse(data=page_json()))
    page = c.get_page("42")
    assert page.body is None and page.parent_id is None
    assert session.calls[0]["params"] == {"expand": "version,ancestors,space"}


def test_create_page_payload():
    c, session = client(FakeResponse(data=page_json("99", 1)))
    page = c.create_page("DOKU", "1001", "Neue Seite", "<p>Inhalt</p>")
    call = session.calls[0]
    assert call["method"] == "POST" and call["url"] == BASE + "/rest/api/content"
    assert call["json"] == {"type": "page", "title": "Neue Seite", "space": {"key": "DOKU"},
                            "body": {"storage": {"value": "<p>Inhalt</p>", "representation": "storage"}},
                            "ancestors": [{"id": "1001"}]}
    assert page.id == "99" and page.parent_id == "1001"


def test_create_page_without_parent():
    c, session = client(FakeResponse(data=page_json("99", 1)))
    c.create_page("DOKU", None, "Oben", "<p/>")
    assert "ancestors" not in session.calls[0]["json"]


def test_update_page_increments_version():
    c, session = client(FakeResponse(data=page_json("42", 4)))
    current = Page("42", "Alt", 3, "7", "DOKU")
    result = c.update_page(current, "Neu", "<p>neu</p>")
    call = session.calls[0]
    assert call["method"] == "PUT" and call["url"] == BASE + "/rest/api/content/42"
    assert call["json"] == {"id": "42", "type": "page", "title": "Neu", "space": {"key": "DOKU"},
                            "version": {"number": 4},
                            "body": {"storage": {"value": "<p>neu</p>", "representation": "storage"}}}
    assert result.version == 4 and result.parent_id == "7"


def test_find_title():
    c, session = client(FakeResponse(data={"results": [page_json("5")]}))
    pages = c.find_title("DOKU", "Seite")
    assert [p.id for p in pages] == ["5"]
    assert session.calls[0]["params"]["spaceKey"] == "DOKU"
    assert session.calls[0]["params"]["title"] == "Seite"


def test_upload_attachment():
    c, session = client(FakeResponse(data={"results": []}))
    c.upload_attachment("42", "cs-abc.png", b"\x89PNG", "image/png")
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == BASE + "/rest/api/content/42/child/attachment"
    assert call["headers"] == {"X-Atlassian-Token": "no-check"}
    assert call["files"] == {"file": ("cs-abc.png", b"\x89PNG", "image/png")}
    assert call["data"]["minorEdit"] == "true"


def test_attachment_names_paginates():
    c, session = client(FakeResponse(data={"results": [{"title": "a.png"}, {"title": "b.png"}],
                                           "_links": {"next": "/x"}}),
                        FakeResponse(data={"results": [{"title": "c.png"}], "_links": {}}))
    assert c.attachment_names("42") == {"a.png", "b.png", "c.png"}
    assert [call["params"]["start"] for call in session.calls] == [0, 2]


def test_spaces_with_personal_space():
    c, _ = client(FakeResponse(data={"results": [{"key": "DOKU", "name": "Doku"}], "_links": {}}),
                  FakeResponse(data={"username": "anna", "displayName": "Anna"}),
                  FakeResponse(data={"key": "~anna", "name": "Anna"}))
    assert c.spaces() == [{"key": "~anna", "name": "Anna", "personal": True},
                          {"key": "DOKU", "name": "Doku", "personal": False}]


def test_search_pages_builds_safe_cql():
    c, session = client(FakeResponse(data={"results": [
        {"id": 5, "title": "Treffer", "ancestors": [{"title": "A"}, {"title": "B"}, {"title": "C"}]}]}))
    result = c.search_pages('DO"KU', 'Proto"koll*')
    cql = session.calls[0]["params"]["cql"]
    assert cql == 'space = "DOKU" and type = page and title ~ "Proto koll*" order by lastmodified desc'
    assert result == [{"id": "5", "title": "Treffer", "path": "B / C"}]
