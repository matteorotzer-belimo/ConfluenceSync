"""Secrets (Confluence token, Notion token) in the Windows Credential Manager via keyring."""
from __future__ import annotations

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from .. import APP_NAME

CONFLUENCE_PAT = "confluence_pat"
NOTION_TOKEN = "notion_token"


def get(name: str) -> str | None:
    try:
        return keyring.get_password(APP_NAME, name)
    except KeyringError:
        return None


def set(name: str, value: str) -> None:  # noqa: A001 - mirrors the keyring API
    keyring.set_password(APP_NAME, name, value)


def delete(name: str) -> None:
    try:
        keyring.delete_password(APP_NAME, name)
    except (PasswordDeleteError, KeyringError):
        pass


def has(name: str) -> bool:
    return bool(get(name))
