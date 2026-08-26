# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class ClientInfo(TypedDict, total=False):
    alias: str
    allow: int
    client_type: int
    cur_conn_time: str
    forbidden: int
    ip: str
    mac: str
    name: str
    type: str


class ClientInfoResponse(TypedDict, total=False):
    clients_info: list[ClientInfo]
    mode: str
    result: int


class FilterMode(TypedDict, total=False):
    mode: str
    result: int


class LoginClientMac(TypedDict, total=False):
    mac: str
    result: int


class TrafficCounters(TypedDict, total=False):
    duration: int
    error_bytes: int
    rx_bytes: int
    rx_tx_bytes: int
    total_duration: int
    total_error_bytes: int
    total_rx_bytes: int
    total_rx_tx_bytes: int
    total_tx_bytes: int
    tx_bytes: int


class TrafficCountersResponse(TypedDict, total=False):
    statistics: TrafficCounters


class TrafficTransportState(TypedDict, total=False):
    rx_status: int
    tx_status: int


class TrafficTransportResponse(TypedDict, total=False):
    traffic_transport_status: TrafficTransportState


class StatisticsNamespace:
    """Safe traffic/client-statistics reads backed by public API evidence."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def traffic(self, *, timeout: float | None = None) -> TrafficCountersResponse:
        """Return current and total byte/duration counters."""

        return cast(
            TrafficCountersResponse,
            self._client.call("statistics", "stat_get_common_data", timeout=timeout),
        )

    def traffic_transport_status(
        self, *, timeout: float | None = None
    ) -> TrafficTransportResponse:
        """Return the router's raw RX/TX activity status values."""

        return cast(
            TrafficTransportResponse,
            self._client.call(
                "statistics",
                "stat_get_traffic_transport_status",
                timeout=timeout,
            ),
        )

    def filter_mode(self, *, timeout: float | None = None) -> FilterMode:
        """Return the MAC-filter mode (`black` or `white` on the tested firmware)."""

        return cast(
            FilterMode,
            self._client.call("statistics", "get_black_white_mode", timeout=timeout),
        )

    def login_client_mac(self, *, timeout: float | None = None) -> LoginClientMac:
        """Return optional management-client MAC metadata.

        The API research explicitly says this value is not reliable enough to
        be the sole identity mechanism for USB management. Treat it as
        diagnostic metadata only.
        """

        return cast(
            LoginClientMac,
            self._client.call("statistics", "get_login_client_mac", timeout=timeout),
        )

    def clients(
        self,
        *,
        request_type: str | None = None,
        timeout: float | None = None,
    ) -> ClientInfoResponse:
        """Return a client inventory/filter view.

        With no `request_type`, use the live-verified body-less GET variant.
        When an advanced caller supplies a `request_type`, it is passed through
        exactly as a top-level POST field. The SDK deliberately does not invent
        active/inactive/allow/forbidden aliases until those raw request-type
        tokens are normalized as a stable public contract.
        """

        if request_type is None:
            return cast(
                ClientInfoResponse,
                self._client.call(
                    "statistics",
                    "get_conn_clients_info",
                    timeout=timeout,
                ),
            )

        if not isinstance(request_type, str):
            raise TypeError("request_type must be a str or None")
        if not request_type.strip():
            raise ValueError("request_type must not be empty")

        return cast(
            ClientInfoResponse,
            self._client.call(
                "statistics",
                "get_conn_clients_info",
                data={"request_type": request_type},
                timeout=timeout,
            ),
        )
