# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class TR069Config(TypedDict, total=False):
    acs_password: str
    acs_url: str
    acs_username: str
    custom_notify_json: str
    enable: int
    periodic_inform_enable: int
    periodic_inform_interval: int
    periodic_notify_enable: int
    periodic_notify_interval: int
    req_authtype: int
    req_password: str
    req_username: str
    result: int


class TR069XMPPConfig(TypedDict, total=False):
    alias: str
    connect_attempt: int
    domain: str
    enable: int
    keepalive_interval: int
    password: str
    resource: str
    result: int
    retry_initial_interval: int
    retry_interval_multiplier: int
    retry_max_interval: int
    server: list[dict[str, Any]]
    server_algorithm: str
    username: str
    usetls: int
    xmpp_allowed_jid: str
    xmpp_loglevel: int


class TR069Namespace:
    """Read-only TR-069/XMPP configuration helpers.

    Both getters can return credentials. They are explicit configuration
    surfaces and are intentionally separate from ordinary device diagnostics.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def config(self, *, timeout: float | None = None) -> TR069Config:
        """Return the raw TR-069 ACS configuration, including secret fields."""

        return cast(
            TR069Config,
            self._client.call("tr069", "get_config", timeout=timeout),
        )

    def xmpp_config(self, *, timeout: float | None = None) -> TR069XMPPConfig:
        """Return the raw TR-069 XMPP configuration, including secret fields."""

        return cast(
            TR069XMPPConfig,
            self._client.call("tr069", "get_xmpp_config", timeout=timeout),
        )
