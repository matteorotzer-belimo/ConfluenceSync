"""Local SQLite database: which source page is published where, and the history of runs."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

SCHEMA = """
CREATE TABLE IF NOT EXISTS mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_title TEXT,
    source_url TEXT,
    source_edited_at TEXT,
    source_hash TEXT,
    confluence_page_id TEXT NOT NULL,
    confluence_url TEXT,
    space TEXT,
    parent_id TEXT,
    title TEXT,
    published_version INTEGER,
    published_hash TEXT,
    status TEXT NOT NULL DEFAULT 'synced',
    last_run_at TEXT,
    last_checked_at TEXT,
    last_error TEXT,
    created_at TEXT,
    UNIQUE (source, source_id)
);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    mapping_id INTEGER,
    source TEXT,
    source_id TEXT,
    title TEXT,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    message TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Mapping(BaseModel):
    id: int | None = None
    source: str
    source_id: str
    source_title: str | None = None
    source_url: str | None = None
    source_edited_at: str | None = None
    source_hash: str | None = None
    confluence_page_id: str
    confluence_url: str | None = None
    space: str | None = None
    parent_id: str | None = None
    title: str | None = None
    published_version: int | None = None
    published_hash: str | None = None
    status: str = "synced"
    last_run_at: str | None = None
    last_checked_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None


class Run(BaseModel):
    id: int
    at: str
    mapping_id: int | None
    source: str | None
    source_id: str | None
    title: str | None
    action: str
    result: str
    message: str | None


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, args)
            rows = cur.fetchall()
            self._conn.commit()
            return rows

    # ---- mappings ----------------------------------------------------------

    def mappings(self) -> list[Mapping]:
        return [Mapping(**dict(r)) for r in self._query("SELECT * FROM mappings ORDER BY last_run_at DESC")]

    def get(self, mapping_id: int) -> Mapping | None:
        rows = self._query("SELECT * FROM mappings WHERE id = ?", (mapping_id,))
        return Mapping(**dict(rows[0])) if rows else None

    def by_source(self, source: str, source_id: str) -> Mapping | None:
        rows = self._query("SELECT * FROM mappings WHERE source = ? AND source_id = ?", (source, source_id))
        return Mapping(**dict(rows[0])) if rows else None

    def save(self, mapping: Mapping) -> Mapping:
        data = mapping.model_dump(exclude={"id"})
        if mapping.id is None:
            data["created_at"] = data.get("created_at") or now()
            cols = ", ".join(data)
            marks = ", ".join("?" for _ in data)
            with self._lock:
                cur = self._conn.execute(f"INSERT INTO mappings ({cols}) VALUES ({marks})", tuple(data.values()))
                self._conn.commit()
                return mapping.model_copy(update={"id": cur.lastrowid, "created_at": data["created_at"]})
        sets = ", ".join(f"{k} = ?" for k in data)
        self._query(f"UPDATE mappings SET {sets} WHERE id = ?", (*data.values(), mapping.id))
        return mapping

    def delete(self, mapping_id: int) -> None:
        self._query("DELETE FROM mappings WHERE id = ?", (mapping_id,))

    # ---- history -----------------------------------------------------------

    def add_run(self, action: str, result: str, message: str = "", mapping: Mapping | None = None,
                source: str | None = None, source_id: str | None = None, title: str | None = None) -> None:
        self._query("INSERT INTO sync_runs (at, mapping_id, source, source_id, title, action, result, message) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (now(), mapping.id if mapping else None, mapping.source if mapping else source,
                     mapping.source_id if mapping else source_id,
                     (mapping.title if mapping else None) or title, action, result, message))

    def runs(self, limit: int = 100) -> list[Run]:
        return [Run(**dict(r)) for r in self._query("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,))]
