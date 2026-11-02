from __future__ import annotations

import keyring.core
from keyring.errors import KeyringError

from confluencesync import APP_NAME
from confluencesync.auth import secrets


def test_set_get_has_delete(memory_keyring):
    assert secrets.get(secrets.CONFLUENCE_PAT) is None
    assert not secrets.has(secrets.CONFLUENCE_PAT)
    secrets.set(secrets.CONFLUENCE_PAT, "pat-synthetic")
    secrets.set(secrets.NOTION_TOKEN, "ntn_synthetic")
    assert memory_keyring.values == {(APP_NAME, "confluence_pat"): "pat-synthetic",
                                     (APP_NAME, "notion_token"): "ntn_synthetic"}
    assert secrets.get(secrets.CONFLUENCE_PAT) == "pat-synthetic"
    assert secrets.has(secrets.NOTION_TOKEN)
    secrets.delete(secrets.CONFLUENCE_PAT)
    assert secrets.get(secrets.CONFLUENCE_PAT) is None
    assert secrets.has(secrets.NOTION_TOKEN)


def test_delete_missing_secret_is_ignored(memory_keyring):
    secrets.delete(secrets.NOTION_TOKEN)
    assert memory_keyring.values == {}


def test_empty_secret_counts_as_missing():
    secrets.set(secrets.NOTION_TOKEN, "")
    assert not secrets.has(secrets.NOTION_TOKEN)


def test_backend_errors_are_handled(monkeypatch, memory_keyring):
    def broken(*_args):
        raise KeyringError("locked")

    monkeypatch.setattr(memory_keyring, "get_password", broken)
    monkeypatch.setattr(memory_keyring, "delete_password", broken)
    assert keyring.core.get_keyring() is memory_keyring
    assert secrets.get(secrets.CONFLUENCE_PAT) is None
    assert not secrets.has(secrets.CONFLUENCE_PAT)
    secrets.delete(secrets.CONFLUENCE_PAT)
