"""Where the app keeps its local data (settings, database, logs, token cache)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME


def data_dir() -> Path:
    """%APPDATA%\\ConfluenceSync, or CONFLUENCESYNC_HOME if set (tests, development)."""
    override = os.environ.get("CONFLUENCESYNC_HOME")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_dir() -> Path:
    """Folder with bundled files (static UI); works from source and inside the PyInstaller exe."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "confluencesync"
    return Path(__file__).resolve().parent
