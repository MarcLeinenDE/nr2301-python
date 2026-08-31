# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


ClientRequestType = Literal[
    "get_active_users",
    "get_inactive_users",
    "get_allow_users",
    "get_forbidden_users",
]


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
    """Traffic/client-statistics helpers backed by public API evidence."""

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

        With no `request_type`, use the independently live-verified body-less
        GET variant.

        Advanced callers may pass a raw `request_type` string through exactly.
        For the four shipped-frontend values, prefer the typed convenience
        helpers `active_clients()`, `inactive_clients()`, `allow_clients()` and
        `forbidden_clients()`.
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

    def client_view(
        self,
        request_type: ClientRequestType,
        *,
        timeout: float | None = None,
    ) -> ClientInfoResponse:
        """Return one of the four exact shipped-frontend client views."""

        if request_type not in {
            "get_active_users",
            "get_inactive_users",
            "get_allow_users",
            "get_forbidden_users",
        }:
            raise ValueError(f"unsupported normalized client request_type: {request_type!r}")
        return self.clients(request_type=request_type, timeout=timeout)

    def active_clients(self, *, timeout: float | None = None) -> ClientInfoResponse:
        """Return the explicit `get_active_users` client view."""

        return self.client_view("get_active_users", timeout=timeout)

    def inactive_clients(self, *, timeout: float | None = None) -> ClientInfoResponse:
        """Return the explicit inactive/offline `get_inactive_users` view."""

        return self.client_view("get_inactive_users", timeout=timeout)

    def allow_clients(self, *, timeout: float | None = None) -> ClientInfoResponse:
        """Return the mode-sensitive explicit `get_allow_users` view."""

        return self.client_view("get_allow_users", timeout=timeout)

    def forbidden_clients(self, *, timeout: float | None = None) -> ClientInfoResponse:
        """Return the mode-sensitive explicit `get_forbidden_users` view."""

        return self.client_view("get_forbidden_users", timeout=timeout)
