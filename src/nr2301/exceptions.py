# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any


class NR2301Error(Exception):
    """Base exception for the SDK."""


class TransportError(NR2301Error):
    """HTTP/network transport failed."""


class ProtocolError(NR2301Error):
    """The router response did not match the expected transport protocol."""


class AuthenticationError(NR2301Error):
    """Administrator authentication failed."""

    def __init__(self, message: str, *, result: int | None = None) -> None:
        super().__init__(message)
        self.result = result


class APIError(NR2301Error):
    """A method-specific API operation reported failure.

    The generic transport layer intentionally does not raise this based on a
    guessed universal `result` convention. High-level namespace helpers may
    use it when a method's semantics are documented.
    """

    def __init__(
        self,
        message: str,
        *,
        method_id: str | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.method_id = method_id
        self.response = response
