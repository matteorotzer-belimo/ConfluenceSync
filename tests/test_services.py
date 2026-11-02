from __future__ import annotations

from pathlib import Path

import pytest

from confluencesync.auth import secrets as keyring_secrets
from confluencesync.confluence.client import ConfluenceError
from confluencesync.connectors.base import SourceError
from confluencesync.connectors.onenote import OneNoteConnector
from confluencesync.demo import FakeConfluence, demo_png
from confluencesync.model import images
from confluencesync.services import MemorySecrets, Services, UserError
from confluencesync.sync import planner

TOKEN = "pat-Synthetic-Secret-987654"
NOTION_TOKEN = "ntn_SyntheticNotionToken123"


def all_file_bytes(folder: Path) -> list[tuple[Path, bytes]]:
    return [(p, p.read_bytes()) for p in folder.rglob("*") if p.is_file()]


def assert_not_on_disk(folder: Path, secret: str) -> None:
    for path, data in all_file_bytes(folder):
        assert secret.encode() not in data, f"secret found in {path}"
        assert secret.encode("utf-16-le") not in data, f"secret found in {path}"


@pytest.fixture
def demo_services(tmp_path):
    services = Services(tmp_path / "data", demo=True)
    yield services
    services.store.close()


@pytest.fixture
def connected(demo_services):
    demo_services.connect_confluence("https://confluence.example.com/", TOKEN)
    return demo_services


class FakeNotion:
    def __init__(self, token: str, fail: bool = False):
        self.token = token
        self.fail = fail
        self.source = "notion"

    def me(self):
        if self.fail:
            raise SourceError("Notion lehnt den Token ab. Ist er korrekt kopiert?")
        return {"name": "Integration", "workspace": "Team"}

    def page_info(self, page_id):
        return None


class FakeAuth:
    def __init__(self, client_id, tenant, signed_in=True, fail=False):
        self.client_id, self.tenant = client_id, tenant
        self.signed_in, self.fail = signed_in, fail
        self.logged_out = False

    def account(self):
        return {"username": "anna@example.com"} if self.signed_in else None

    def token(self):
        return "graph-token"

    def login_interactive(self):
        if self.fail:
            raise RuntimeError("Die Anmeldung wurde abgebrochen.")
        self.signed_in = True

    def logout(self):
        self.logged_out = True
        self.signed_in = False


# --------------------------------------------------------------------------- Confluence connection


def test_demo_services_start_without_connection(demo_services):
    st = demo_services.status()
    assert not st.confluence_connected and not st.notion_connected and not st.any_source
    assert [key for key, _ in demo_services.sources()] == ["demo", "onenote", "notion"]
    assert isinstance(demo_services.secrets, MemorySecrets)
    with pytest.raises(UserError, match="Confluence ist noch nicht verbunden"):
        demo_services.prepare("demo", "demo-besprechung")
    with pytest.raises(UserError, match="Confluence ist noch nicht verbunden"):
        demo_services.check_all()


def test_connect_confluence_input_validation(demo_services):
    with pytest.raises(UserError, match="Adresse"):
        demo_services.connect_confluence("  ", TOKEN)
    with pytest.raises(UserError, match="Zugriffstoken"):
        demo_services.connect_confluence("https://confluence.example.com", "  ")


def test_connect_confluence_stores_token_only_in_secrets(tmp_path):
    seen = []
    secrets = MemorySecrets()
    fake = FakeConfluence()

    def factory(url, token):
        seen.append((url, token))
        return fake

    data = tmp_path / "data"
    services = Services(data, secrets=secrets, confluence_factory=factory)
    name = services.connect_confluence("https://confluence.example.com/", f"  {TOKEN}  ")
    assert name == "Demo Nutzerin"
    assert seen == [("https://confluence.example.com", TOKEN)]
    assert secrets.values == {keyring_secrets.CONFLUENCE_PAT: TOKEN}
    settings_text = (data / "settings.json").read_text(encoding="utf-8")
    assert "confluence.example.com" in settings_text and "Demo Nutzerin" in settings_text
    assert services.status().confluence_connected
    assert services.test_confluence() == "Demo Nutzerin"
    # publish something so the database has content too
    prepared = services.prepare("demo", "demo-besprechung")
    services.publish(prepared, "publish", space="DOKU")
    services.store.close()
    assert_not_on_disk(data, TOKEN)


def test_connect_confluence_reuses_saved_token(demo_services):
    demo_services.connect_confluence("https://confluence.example.com", TOKEN)
    assert demo_services.connect_confluence("https://confluence.example.com", "") == "Demo Nutzerin"
    assert demo_services.secrets.get(keyring_secrets.CONFLUENCE_PAT) == TOKEN


def test_connect_confluence_with_real_keyring_module_uses_memory_backend(tmp_path, memory_keyring):
    data = tmp_path / "data"
    services = Services(data, confluence_factory=lambda url, token: FakeConfluence())
    services.connect_confluence("https://confluence.example.com", TOKEN)
    assert memory_keyring.values == {("ConfluenceSync", keyring_secrets.CONFLUENCE_PAT): TOKEN}
    services.store.close()
    assert_not_on_disk(data, TOKEN)


def test_connect_confluence_failure_does_not_store_token(tmp_path):
    def factory(url, token):
        raise ConfluenceError("GET /user/current -> HTTP 401", 401)

    secrets = MemorySecrets()
    services = Services(tmp_path / "data", secrets=secrets, confluence_factory=factory)
    with pytest.raises(UserError, match="lehnt den Zugriffstoken ab"):
        services.connect_confluence("https://confluence.example.com", TOKEN)
    assert secrets.values == {}
    assert services.config.confluence_url == ""
    services.store.close()


def test_disconnect_confluence(connected):
    connected.disconnect_confluence()
    assert not connected.status().confluence_connected
    assert connected.config.confluence_user == ""
    assert connected.secrets.get(keyring_secrets.CONFLUENCE_PAT) is None


def test_spaces_and_search(connected):
    assert [s["key"] for s in connected.spaces()] == ["~demo", "DOKU"]
    assert [p["title"] for p in connected.search_pages("DOKU", "besprech")] == ["Besprechungen"]


# --------------------------------------------------------------------------- full demo flow


def test_full_demo_flow(connected, tmp_path):
    services = connected
    prepared = services.prepare("demo", "demo-besprechung")
    assert prepared.action == "create"
    image = images(prepared.doc)[0]
    assert services.image(prepared, image.filename) == demo_png()

    mapping = services.publish(prepared, "publish", space="DOKU", space_name="Team-Dokumentation",
                               parent_id="1001", parent_title="Besprechungen")
    assert mapping.status == planner.SYNCED
    assert services.published_ids("demo") == {"demo-besprechung"}
    assert services.config.recent_parents[0] == {"space": "DOKU", "space_name": "Team-Dokumentation",
                                                 "id": "1001", "title": "Besprechungen"}
    page = services.fake.pages[mapping.confluence_page_id]
    assert page.parent_id == "1001"

    assert [m.status for m in services.check_all()] == [planner.SYNCED]

    services.demo_edit_confluence(mapping.id)
    assert [m.status for m in services.check_all()] == [planner.CONFLUENCE_CHANGED]
    assert services.publications()[0].status == planner.CONFLUENCE_CHANGED

    services.demo_edit_source("demo-besprechung")
    assert [m.status for m in services.check_all()] == [planner.REVIEW]

    conflict = services.prepare("demo", "demo-besprechung")
    with pytest.raises(UserError, match="von Hand geändert"):
        services.publish(conflict, "publish")
    with pytest.raises(UserError, match="Unbekannte Aktion"):
        services.publish(conflict, "delete")
    services.publish(conflict, "overwrite")
    assert [m.status for m in services.check_all()] == [planner.SYNCED]
    assert "Neuer Punkt aus der Quelle." in services.fake.pages[mapping.confluence_page_id].body

    history = services.history()
    assert [(r.action, r.result) for r in history] == [("update", "ok"), ("update", "error"), ("create", "ok")]

    services.forget(mapping.id)
    assert services.publications() == []
    assert services.history()[0].action == "forget"
    assert services.history()[0].title == "Teamsitzung 28. Oktober"
    assert mapping.confluence_page_id in services.fake.pages     # the page itself is kept
    services.forget(9999)                                        # unknown id: no error
    assert services.history()[0].action == "forget" and len(services.history()) == 4


def test_demo_data_starts_fresh(tmp_path):
    first = Services(tmp_path / "data", demo=True)
    first.connect_confluence("https://confluence.example.com", TOKEN)
    first.publish(first.prepare("demo", "demo-idee"), "publish", space="DOKU")
    assert len(first.publications()) == 1
    first.store.close()
    second = Services(tmp_path / "data", demo=True)
    assert second.publications() == []
    assert not second.status().confluence_connected
    second.store.close()


def test_check_all_with_unconnected_source(connected):
    connected.publish(connected.prepare("demo", "demo-idee"), "publish", space="DOKU")
    mapping = connected.publications()[0]
    connected.store.save(mapping.model_copy(update={"source": "notion"}))
    result = connected.check_all()
    assert result[0].status == planner.UNKNOWN


# --------------------------------------------------------------------------- sources


def test_missing_source_connections(demo_services):
    with pytest.raises(UserError, match="OneNote ist noch nicht verbunden"):
        demo_services.connector("onenote")
    with pytest.raises(UserError, match="Notion ist noch nicht verbunden"):
        demo_services.connector("notion")
    with pytest.raises(UserError, match="Unbekannte Quelle"):
        demo_services.connector("evernote")
    assert demo_services.connector("onenote", required=False) is None
    assert demo_services.connector("notion", required=False) is None
    with pytest.raises(UserError, match="Notion ist noch nicht verbunden"):
        demo_services.children("notion")
    with pytest.raises(UserError, match="Client-ID"):
        demo_services.login_onenote()
    with pytest.raises(UserError, match="Client-ID"):
        demo_services.configure_onenote("  ")


def test_demo_source_navigation(demo_services):
    root = demo_services.children("demo")
    assert [n.id for n in root] == ["notebook:team"]
    sections = demo_services.children("demo", "notebook:team")
    assert [n.kind for n in sections] == ["section", "section"]
    pages = demo_services.children("demo", "section:projekte")
    assert {n.id for n in pages} == {"demo-idee", "demo-howto"}
    assert [n.id for n in demo_services.search("demo", "onboarding")] == ["demo-idee"]


def test_notion_connection(tmp_path):
    secrets = MemorySecrets()
    services = Services(tmp_path / "data", secrets=secrets, notion_factory=lambda token: FakeNotion(token))
    with pytest.raises(UserError, match="Notion-Token"):
        services.connect_notion("  ")
    assert services.connect_notion(f" {NOTION_TOKEN} ") == {"name": "Integration", "workspace": "Team"}
    assert secrets.get(keyring_secrets.NOTION_TOKEN) == NOTION_TOKEN
    assert services.status().notion_connected and services.status().any_source
    assert services.connector("notion").token == NOTION_TOKEN
    assert services.test_notion()["name"] == "Integration"
    services.disconnect_notion()
    assert not services.status().notion_connected
    services.store.close()
    assert_not_on_disk(tmp_path / "data", NOTION_TOKEN)


def test_notion_connection_failure(tmp_path):
    secrets = MemorySecrets()
    services = Services(tmp_path / "data", secrets=secrets,
                        notion_factory=lambda token: FakeNotion(token, fail=True))
    with pytest.raises(UserError, match="lehnt den Token ab"):
        services.connect_notion(NOTION_TOKEN)
    assert secrets.values == {}
    services.store.close()


def test_onenote_configuration_and_login(tmp_path):
    created = []

    def auth_factory(client_id, tenant):
        auth = FakeAuth(client_id, tenant, signed_in=False)
        created.append(auth)
        return auth

    services = Services(tmp_path / "data", secrets=MemorySecrets(), auth_factory=auth_factory)
    assert services.auth() is None
    services.configure_onenote(" client-123 ", "")
    assert services.config.ms_client_id == "client-123" and services.config.ms_tenant_id == "organizations"
    assert services.status().onenote_configured and services.status().onenote_account is None
    assert services.login_onenote() == "anna@example.com"
    assert services.auth() is created[0]                     # cached while the settings are the same
    assert services.status().onenote_account == "anna@example.com"
    assert isinstance(services.connector("onenote"), OneNoteConnector)
    services.logout_onenote()
    assert created[0].logged_out
    services.configure_onenote("other-client", "tenant-x")
    assert services.auth() is created[1] and created[1].tenant == "tenant-x"
    services.store.close()


def test_onenote_login_failure(tmp_path):
    services = Services(tmp_path / "data", secrets=MemorySecrets(),
                        auth_factory=lambda c, t: FakeAuth(c, t, signed_in=False, fail=True))
    services.configure_onenote("client-123")
    with pytest.raises(UserError, match="abgebrochen"):
        services.login_onenote()
    services.store.close()


def test_check_update_delegates(monkeypatch):
    from confluencesync import updates

    monkeypatch.setattr(updates, "latest_release", lambda: {"version": "9.9.9", "url": "https://x"})
    assert Services.check_update() == {"version": "9.9.9", "url": "https://x"}
