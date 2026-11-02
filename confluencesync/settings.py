"""Non-secret settings, stored as settings.json in the app data folder.

Secrets (tokens) are never stored here, see auth/secrets.py.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    confluence_url: str = ""
    confluence_user: str = ""
    default_space: str = ""
    default_space_name: str = ""
    default_parent_id: str = ""
    default_parent_title: str = ""
    ms_client_id: str = ""
    ms_tenant_id: str = "organizations"
    tutorial_completed: bool = False
    check_updates: bool = True
    recent_parents: list[dict] = Field(default_factory=list)


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> Settings:
        try:
            return Settings(**json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return Settings()

    @property
    def value(self) -> Settings:
        return self._settings

    def update(self, **changes) -> Settings:
        with self._lock:
            data = {**self._settings.model_dump(), **changes}
            self._settings = Settings(**data)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._settings.model_dump(), ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, self.path)
            return self._settings

    def remember_parent(self, space: str, space_name: str, parent_id: str, parent_title: str) -> None:
        entry = {"space": space, "space_name": space_name, "id": parent_id, "title": parent_title}
        recent = [entry] + [r for r in self._settings.recent_parents
                            if not (r.get("space") == space and r.get("id") == parent_id)]
        self.update(recent_parents=recent[:8])
