"""Microsoft sign-in with MSAL (public client, delegated permissions, no client secret).

The token cache is encrypted with Windows DPAPI (msal-extensions) and stored in the app data
folder. If encryption is not available the cache is kept in memory only (never in plain text).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import msal

SCOPES = ["Notes.Read", "User.Read"]
log = logging.getLogger(__name__)


def build_cache(path: Path) -> msal.TokenCache:
    try:
        from msal_extensions import PersistedTokenCache, build_encrypted_persistence
        return PersistedTokenCache(build_encrypted_persistence(str(path)))
    except Exception as exc:  # noqa: BLE001 - any failure means: no persistent cache
        log.warning("encrypted token cache not available (%s); using memory only", type(exc).__name__)
        return msal.SerializableTokenCache()


class MicrosoftAuth:
    def __init__(self, client_id: str, tenant: str, cache_path: Path, app=None):
        tenant = (tenant or "organizations").strip()
        self.client_id = client_id.strip()
        self.tenant = tenant
        self.app = app or msal.PublicClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{tenant}",
            token_cache=build_cache(cache_path))
        self._lock = threading.Lock()

    def account(self) -> dict | None:
        accounts = self.app.get_accounts()
        return accounts[0] if accounts else None

    def token(self) -> str | None:
        """Access token from the cache (refreshed silently), or None if a new sign-in is needed."""
        account = self.account()
        if not account:
            return None
        with self._lock:
            result = self.app.acquire_token_silent(SCOPES, account=account)
        return (result or {}).get("access_token")

    def login_interactive(self, timeout: int = 300) -> dict:
        """Open the system browser for the Microsoft sign-in (redirect to http://localhost)."""
        result = self.app.acquire_token_interactive(SCOPES, prompt="select_account", timeout=timeout)
        if "access_token" not in result:
            raise RuntimeError(describe_error(result))
        return self.account() or {}

    def logout(self) -> None:
        for account in self.app.get_accounts():
            self.app.remove_account(account)


def describe_error(result: dict) -> str:
    code = result.get("error", "")
    text = result.get("error_description", "") or ""
    if "AADSTS700016" in text or "AADSTS90002" in text:
        return "Die Client-ID oder Tenant-ID ist unbekannt. Bitte die Angaben der IT prüfen."
    if "AADSTS65001" in text or "consent" in text.lower():
        return "Für die App fehlt die Zustimmung (Admin-Consent). Bitte bei der IT nachfragen."
    if "AADSTS50011" in text:
        return "Die Weiterleitungsadresse fehlt in der App-Registrierung (http://localhost). Bitte der IT melden."
    if code in ("access_denied", "authorization_pending") or "cancel" in text.lower():
        return "Die Anmeldung wurde abgebrochen."
    if code == "timeout" or "timeout" in text.lower():
        return "Die Anmeldung hat zu lange gedauert. Bitte nochmals versuchen."
    return f"Anmeldung fehlgeschlagen ({code or 'unbekannter Fehler'})."
