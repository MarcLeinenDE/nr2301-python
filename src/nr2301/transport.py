# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import requests

from .exceptions import ProtocolError, TransportError

JSONValue = Any


class HTTPTransport:
    """Low-level NR2301 `/api.cgi` HTTP transport."""

    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api.cgi"

    def call(
        self,
        path: str,
        method: str,
        *,
        data: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        effective_timeout = self.timeout if timeout is None else timeout
        params = {
            "path": path,
            "method": method,
            "timeout": _format_timeout(effective_timeout),
        }
        http_method = "GET" if data is None else "POST"

        kwargs: dict[str, Any] = {
            "params": params,
            "timeout": effective_timeout,
        }
        if data is not None:
            kwargs["json"] = dict(data)

        response = self._request(http_method, self.api_url, **kwargs)
        return self._decode_json_object(response, method_id=f"{path}/{method}")

    def multicall(
        self,
        requests_: Sequence[Mapping[str, Any]],
        *,
        timeout: float | None = None,
    ) -> Any:
        effective_timeout = self.timeout if timeout is None else timeout
        body = {"requests": [dict(item) for item in requests_]}
        response = self._request(
            "POST",
            self.api_url,
            params={"multicalls": 1},
            json=body,
            timeout=effective_timeout,
        )
        return self._decode_json(response, method_id="multicall")

    def close(self) -> None:
        self.session.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise TransportError(str(exc)) from exc

    @staticmethod
    def _decode_json(response: requests.Response, *, method_id: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ProtocolError(f"{method_id} returned non-JSON content") from exc

    @classmethod
    def _decode_json_object(cls, response: requests.Response, *, method_id: str) -> dict[str, Any]:
        payload = cls._decode_json(response, method_id=method_id)
        if not isinstance(payload, dict):
            raise ProtocolError(
                f"{method_id} returned {type(payload).__name__}, expected a JSON object"
            )
        return payload


def _format_timeout(timeout: float) -> str:
    return str(int(timeout)) if float(timeout).is_integer() else str(timeout)
