# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class VPNStatus(TypedDict, total=False):
    result: int
    vpn_status: str


class VPNNamespace:
    """Read-only VPN status helpers backed by live-verified public contracts.

    This initial surface deliberately exposes only connection status. The
    profile-list API is kept out because its response may contain VPN
    passwords/PSKs and should not be pulled into routine SDK diagnostics.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def status(self, *, timeout: float | None = None) -> VPNStatus:
        """Return the raw VPN client connection-status response."""

        return cast(
            VPNStatus,
            self._client.call(
                "cm",
                "get_vpn_client_connect_status",
                timeout=timeout,
            ),
        )

    def profiles(self, *, timeout: float | None = None) -> dict[str, Any]:
        """Return the raw configured VPN client profiles.

        The response may contain VPN passwords and L2TP/IPsec pre-shared keys.
        Applications must treat the returned object as secret-bearing data and
        avoid routine logging or public diagnostics.
        """

        return cast(
            dict[str, Any],
            self._client.call("cm", "get_vpn_clients", timeout=timeout),
        )
