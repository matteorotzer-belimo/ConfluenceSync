"""Shared fixtures: no network, no real keyring, app data in a temporary folder."""
from __future__ import annotations

import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import keyring  # noqa: E402
import keyring.core  # noqa: E402
import pytest  # noqa: E402
from keyring.backend import KeyringBackend  # noqa: E402
from keyring.errors import PasswordDeleteError  # noqa: E402

from confluencesync.demo import DemoConnector, FakeConfluence  # noqa: E402
from confluencesync.model import SourceDocument  # noqa: E402
from confluencesync.store import Store  # noqa: E402


class NetworkBlocked(RuntimeError):
    pass


class MemoryKeyring(KeyringBackend):
    """In-memory keyring backend so tests never touch the Windows Credential Manager."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        self.values[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.values:
            raise PasswordDeleteError("not found")
        del self.values[(service, username)]


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CONFLUENCESYNC_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise NetworkBlocked("network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("requests.Session.request", blocked)


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    backend = MemoryKeyring()
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)
    return backend


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def fake():
    return FakeConfluence()


@pytest.fixture
def demo():
    return DemoConnector()


def make_doc(blocks: list | None = None, **kwargs) -> SourceDocument:
    data = {"source": "demo", "source_id": "doc-1", "title": "Testseite",
            "source_url": "https://example.com/note?a=1&b=2",
            "source_edited_at": datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc),
            "blocks": blocks or []}
    data.update(kwargs)
    return SourceDocument(**data)
