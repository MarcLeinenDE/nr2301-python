# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class DDNSSettings(TypedDict, total=False):
    """Known fields returned by `ddns/get_ddns`."""

    ddns_ipaddr: str
    ddns_state: str
    domain: str
    enabled: str
    password: str
    result: int
    service_name: str
    username: str


class DDNSNamespace:
    """Dynamic-DNS reads backed by the live-verified public contract."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def settings(self, *, timeout: float | None = None) -> DDNSSettings:
        """Return the raw DDNS settings.

        The response can contain DDNS credentials. Applications must treat the
        returned username/password as secrets and avoid routine logging.
        """

        return cast(
            DDNSSettings,
            self._client.call("ddns", "get_ddns", timeout=timeout),
        )
