from __future__ import annotations

import pytest

from confluencesync import GITHUB_REPO, __version__, updates


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.parametrize("text,expected", [
    ("1.2.3", (1, 2, 3)), ("v0.10.1", (0, 10, 1)), ("0.2.0-beta.1", (0, 2, 0)), ("1.2", (1, 2)),
    ("1.2.3.4", (1, 2, 3)), ("garbage", (0,)), ("", (0,)),
])
def test_parse_version(text, expected):
    assert updates.parse_version(text) == expected


def test_is_newer():
    assert updates.is_newer("v0.10.0", "0.9.9")
    assert updates.is_newer("1.0.0", "0.99.99")
    assert not updates.is_newer("0.1.0", "0.1.0")
    assert not updates.is_newer("v0.0.9", "0.1.0")
    assert not updates.is_newer(__version__)
    assert updates.is_newer("v999.0.0")


def test_latest_release_newer():
    session = FakeSession(FakeResponse(200, {"tag_name": "v999.1.0", "html_url": "https://github.com/x/releases/v999.1.0"}))
    assert updates.latest_release(session=session) == {"version": "999.1.0",
                                                       "url": "https://github.com/x/releases/v999.1.0"}
    url, kwargs = session.calls[0]
    assert url == f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    assert kwargs["timeout"] == 4.0


@pytest.mark.parametrize("response", [
    FakeResponse(200, {"tag_name": f"v{__version__}", "html_url": "https://x"}),
    FakeResponse(200, {"tag_name": "v0.0.1"}),
    FakeResponse(200, {}),
    FakeResponse(404, {"message": "Not Found"}),
    FakeResponse(200, ValueError("bad json")),
    ConnectionError("offline"),
])
def test_latest_release_returns_none(response):
    assert updates.latest_release(session=FakeSession(response)) is None


def test_latest_release_without_session_never_raises():
    # the real requests call hits the network guard and must be swallowed
    assert updates.latest_release() is None
