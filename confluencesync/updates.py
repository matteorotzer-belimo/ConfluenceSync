"""Update hint: compare the running version with the latest GitHub release."""
from __future__ import annotations

import re

import requests

from . import GITHUB_REPO, __version__


def parse_version(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(n) for n in numbers[:3]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return parse_version(latest) > parse_version(current)


def latest_release(session=None, timeout: float = 4.0) -> dict | None:
    """{'version': '0.2.0', 'url': ...} if a newer release exists, else None. Never raises."""
    http = session or requests
    try:
        resp = http.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                        headers={"Accept": "application/vnd.github+json"}, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name") or ""
        if tag and is_newer(tag):
            return {"version": tag.lstrip("v"), "url": data.get("html_url")}
    except Exception:  # noqa: BLE001 - the update hint must never break the app
        return None
    return None
