from __future__ import annotations

from typing import Any

import requests


class FakeResponse:
    def __init__(self, payload: Any, *, status_code: int = 200, on_json=None) -> None:
        self._payload = payload
        self.status_code = status_code
        self._on_json = on_json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._on_json is not None:
            self._on_json()
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.cookies = requests.cookies.RequestsCookieJar()
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True
