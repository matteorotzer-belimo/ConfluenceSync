"""Application services: everything the UI does, without any Qt code (easy to test).

Methods may block (network). The UI calls them in a worker thread.
Errors meant for the user are raised as UserError with a German message.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from . import updates
from .auth import secrets as keyring_secrets
from .auth.msal_login import MicrosoftAuth
from .confluence.client import ConfluenceClient, ConfluenceError, friendly_message
from .connectors.base import SourceError, SourceNode
from .connectors.notion import NotionConnector
from .connectors.onenote import OneNoteConnector
from .demo import DemoConnector, FakeConfluence
from .model import SOURCE_LABELS
from .settings import Settings, SettingsStore
from .store import Mapping, Run, Store
from .sync import publisher
from .sync.publisher import Prepared, PublishError

log = logging.getLogger(__name__)


class UserError(Exception):
    """Message for the user (German)."""


class MemorySecrets:
    """Secrets kept in memory only (demo mode and tests)."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)

    def has(self, name: str) -> bool:
        return bool(self.values.get(name))


@dataclass
class Status:
    confluence_connected: bool
    confluence_url: str
    confluence_user: str
    onenote_configured: bool
    onenote_account: str | None
    notion_connected: bool

    @property
    def any_source(self) -> bool:
        return bool(self.onenote_account) or self.notion_connected


def _wrap(exc: Exception) -> UserError:
    if isinstance(exc, ConfluenceError):
        return UserError(friendly_message(exc))
    return UserError(str(exc))


class Services:
    def __init__(self, data_dir: Path, demo: bool = False, secrets=None, confluence_factory=None,
                 notion_factory=None, auth_factory=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.demo = demo
        if demo:  # the fake Confluence lives in memory, so demo data starts fresh every time
            for name in ("demo.db", "demo-settings.json"):
                (self.data_dir / name).unlink(missing_ok=True)
        self.secrets = secrets or (MemorySecrets() if demo else keyring_secrets)
        self.settings = SettingsStore(self.data_dir / ("demo-settings.json" if demo else "settings.json"))
        self.store = Store(self.data_dir / ("demo.db" if demo else "confluencesync.db"))
        self.fake = FakeConfluence() if demo else None
        self.demo_connector = DemoConnector()
        self.confluence_factory = confluence_factory or (
            (lambda url, token: self.fake) if demo else (lambda url, token: ConfluenceClient(url, token)))
        self.notion_factory = notion_factory or (lambda token: NotionConnector(token))
        self.auth_factory = auth_factory or (
            lambda client_id, tenant: MicrosoftAuth(client_id, tenant, self.data_dir / "msal_cache.bin"))
        self._auth: MicrosoftAuth | None = None
        self._auth_key: tuple | None = None
        self._lock = threading.Lock()

    # ---- state ------------------------------------------------------------

    @property
    def config(self) -> Settings:
        return self.settings.value

    def status(self, check_onenote: bool = True) -> Status:
        s = self.config
        account = None
        if check_onenote and s.ms_client_id:
            auth = self.auth()
            info = auth.account() if auth else None
            account = (info or {}).get("username") if info else None
        return Status(
            confluence_connected=bool(s.confluence_url and self.secrets.has(keyring_secrets.CONFLUENCE_PAT)),
            confluence_url=s.confluence_url, confluence_user=s.confluence_user,
            onenote_configured=bool(s.ms_client_id), onenote_account=account,
            notion_connected=self.secrets.has(keyring_secrets.NOTION_TOKEN))

    def sources(self) -> list[tuple[str, str]]:
        """(key, label) of the sources shown in the app."""
        items = [("onenote", SOURCE_LABELS["onenote"]), ("notion", SOURCE_LABELS["notion"])]
        if self.demo:
            items.insert(0, ("demo", SOURCE_LABELS["demo"]))
        return items

    def update_settings(self, **changes) -> Settings:
        return self.settings.update(**changes)

    @staticmethod
    def check_update() -> dict | None:
        return updates.latest_release()

    # ---- Confluence -------------------------------------------------------

    def confluence(self):
        url = self.config.confluence_url
        token = self.secrets.get(keyring_secrets.CONFLUENCE_PAT)
        if not url or not token:
            raise UserError("Confluence ist noch nicht verbunden. Bitte unter «Verbindungen» einrichten.")
        try:
            return self.confluence_factory(url, token)
        except ConfluenceError as exc:
            raise _wrap(exc) from None

    def connect_confluence(self, url: str, token: str | None = None) -> str:
        """Test the connection and save URL + token. Returns the display name."""
        url = (url or "").strip().rstrip("/")
        token = (token or "").strip() or self.secrets.get(keyring_secrets.CONFLUENCE_PAT)
        if not url:
            raise UserError("Bitte die Adresse von Confluence eingeben.")
        if not token:
            raise UserError("Bitte den persönlichen Zugriffstoken einfügen.")
        try:
            client = self.confluence_factory(url, token)
            user = client.current_user()
        except ConfluenceError as exc:
            raise _wrap(exc) from None
        self.secrets.set(keyring_secrets.CONFLUENCE_PAT, token)
        self.settings.update(confluence_url=getattr(client, "base", url), confluence_user=user.get("name") or "")
        return user.get("name") or ""

    def test_confluence(self) -> str:
        try:
            return self.confluence().current_user().get("name") or ""
        except ConfluenceError as exc:
            raise _wrap(exc) from None

    def disconnect_confluence(self) -> None:
        self.secrets.delete(keyring_secrets.CONFLUENCE_PAT)
        self.settings.update(confluence_user="")

    def spaces(self) -> list[dict]:
        try:
            return self.confluence().spaces()
        except ConfluenceError as exc:
            raise _wrap(exc) from None

    def search_pages(self, space: str, query: str = "") -> list[dict]:
        try:
            return self.confluence().search_pages(space, query)
        except ConfluenceError as exc:
            raise _wrap(exc) from None

    # ---- OneNote ----------------------------------------------------------

    def auth(self) -> MicrosoftAuth | None:
        s = self.config
        if not s.ms_client_id:
            return None
        with self._lock:
            key = (s.ms_client_id, s.ms_tenant_id)
            if self._auth is None or self._auth_key != key:
                self._auth = self.auth_factory(s.ms_client_id, s.ms_tenant_id)
                self._auth_key = key
            return self._auth

    def configure_onenote(self, client_id: str, tenant_id: str = "") -> None:
        client_id = (client_id or "").strip()
        if not client_id:
            raise UserError("Bitte die Client-ID (Anwendungs-ID) eingeben.")
        self.settings.update(ms_client_id=client_id, ms_tenant_id=(tenant_id or "").strip() or "organizations")

    def login_onenote(self) -> str:
        """Interactive Microsoft sign-in in the system browser (blocks until done)."""
        auth = self.auth()
        if auth is None:
            raise UserError("Bitte zuerst Client-ID und Tenant-ID eintragen.")
        try:
            auth.login_interactive()
        except Exception as exc:  # noqa: BLE001 - msal raises various types; message is German already
            raise UserError(str(exc) or "Die Anmeldung bei Microsoft hat nicht geklappt.") from None
        account = auth.account() or {}
        return account.get("username") or ""

    def logout_onenote(self) -> None:
        auth = self.auth()
        if auth:
            auth.logout()

    # ---- Notion -----------------------------------------------------------

    def connect_notion(self, token: str) -> dict:
        token = (token or "").strip()
        if not token:
            raise UserError("Bitte den Notion-Token einfügen.")
        try:
            info = self.notion_factory(token).me()
        except SourceError as exc:
            raise _wrap(exc) from None
        self.secrets.set(keyring_secrets.NOTION_TOKEN, token)
        return info

    def test_notion(self) -> dict:
        try:
            return self.connector("notion").me()
        except SourceError as exc:
            raise _wrap(exc) from None

    def disconnect_notion(self) -> None:
        self.secrets.delete(keyring_secrets.NOTION_TOKEN)

    # ---- sources ----------------------------------------------------------

    def connector(self, source: str, required: bool = True):
        if source == "demo":
            return self.demo_connector
        if source == "onenote":
            auth = self.auth()
            if auth and auth.account():
                return OneNoteConnector(auth.token)
            if required:
                raise UserError("OneNote ist noch nicht verbunden. Bitte unter «Verbindungen» anmelden.")
            return None
        if source == "notion":
            token = self.secrets.get(keyring_secrets.NOTION_TOKEN)
            if token:
                return self.notion_factory(token)
            if required:
                raise UserError("Notion ist noch nicht verbunden. Bitte unter «Verbindungen» einrichten.")
            return None
        raise UserError("Unbekannte Quelle.")

    def children(self, source: str, parent: str | None = None) -> list[SourceNode]:
        try:
            return self.connector(source).children(parent)
        except SourceError as exc:
            raise _wrap(exc) from None

    def search(self, source: str, query: str) -> list[SourceNode]:
        try:
            return self.connector(source).search(query)
        except SourceError as exc:
            raise _wrap(exc) from None

    def published_ids(self, source: str) -> set[str]:
        return {m.source_id for m in self.store.mappings() if m.source == source}

    # ---- preview and publish ---------------------------------------------

    def prepare(self, source: str, source_id: str) -> Prepared:
        try:
            return publisher.prepare(self.store, self.confluence(), self.connector(source), source_id)
        except (PublishError, ConfluenceError, SourceError) as exc:
            raise _wrap(exc) from None

    def image(self, prepared: Prepared, filename: str) -> bytes:
        try:
            return publisher.image_bytes(prepared, self.connector(prepared.doc.source), filename)
        except (PublishError, SourceError) as exc:
            raise _wrap(exc) from None

    def publish(self, prepared: Prepared, decision: str = "publish", title: str = "", space: str = "",
                space_name: str = "", parent_id: str = "", parent_title: str = "") -> Mapping:
        if decision not in ("publish", "overwrite", "keep_confluence"):
            raise UserError("Unbekannte Aktion.")
        try:
            mapping = publisher.publish(self.store, self.confluence(), self.connector(prepared.doc.source),
                                        prepared, decision, title, space, parent_id)
        except (PublishError, ConfluenceError, SourceError) as exc:
            raise _wrap(exc) from None
        if prepared.action == "create" and space:
            self.settings.remember_parent(space, space_name or space, parent_id, parent_title)
        return mapping

    # ---- publications -----------------------------------------------------

    def publications(self) -> list[Mapping]:
        return self.store.mappings()

    def check_all(self) -> list[Mapping]:
        confluence = self.confluence()
        result = []
        for mapping in self.store.mappings():
            connector = self.connector(mapping.source, required=False)
            result.append(publisher.refresh_status(self.store, confluence, connector, mapping))
        return result

    def forget(self, mapping_id: int) -> None:
        mapping = self.store.get(mapping_id)
        if mapping:
            self.store.delete(mapping_id)
            self.store.add_run("forget", "ok", "Verknüpfung entfernt (Confluence-Seite bleibt bestehen)",
                               source=mapping.source, source_id=mapping.source_id, title=mapping.title)

    def history(self, limit: int = 100) -> list[Run]:
        return self.store.runs(limit)

    # ---- demo helpers (simulate changes to try the update flow) ----------

    def demo_edit_confluence(self, mapping_id: int) -> None:
        mapping = self.store.get(mapping_id)
        page = self.fake.pages[mapping.confluence_page_id]
        self.fake.edit_by_hand(page.id, page.body + "<p>Von Hand in Confluence ergänzt.</p>")

    def demo_edit_source(self, source_id: str) -> None:
        from datetime import datetime, timezone

        page = self.demo_connector.pages[source_id]
        page["html"] = page["html"].replace("</body>", "<p>Neuer Punkt aus der Quelle.</p></body>")
        page["edited"] = datetime.now(timezone.utc).replace(microsecond=0)
