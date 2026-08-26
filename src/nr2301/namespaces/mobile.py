# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class CellularBasicInfo(TypedDict, total=False):
    """Known fields from `cm/get_cell_info.celluar_basic_info`."""

    data_mode: int
    network_name: str
    roaming: int
    roaming_network_name: str


class SignalInfo(TypedDict, total=False):
    """Known fields from one `cm/get_cell_info.signal_info` item."""

    level: int
    rat: str


class CellInfo(TypedDict, total=False):
    """Known response fields returned by `cm/get_cell_info`."""

    celluar_basic_info: CellularBasicInfo
    signal_info: list[SignalInfo]


class WANContext(TypedDict, total=False):
    """Known fields from one `cm/get_current_wan_info.contextlist` item."""

    connection_status: int
    internet_status: int
    ipv4_dns1: str
    ipv4_dns2: str
    ipv4_gateway: str
    ipv4_ip: str
    ipv4_submask: str
    ipv6_dns1: str
    ipv6_dns2: str
    ipv6_gateway: str
    ipv6_ip: str


class CurrentWANInfo(TypedDict, total=False):
    """Known response fields returned by `cm/get_current_wan_info`."""

    contextlist: list[WANContext]
    wan_name: str
    wan_type: str


class AvailableNetworkModes(TypedDict, total=False):
    """Known response fields returned by `cm/get_available_network_mode`."""

    network_modes: list[str]
    result: int


class NetworkSettings(TypedDict, total=False):
    """Known fields from `cm/get_network_settings.network_settings`."""

    connect_mode: str
    data_roaming: str
    network_mode: str
    profile: dict[str, Any]


class NetworkSettingsResponse(TypedDict, total=False):
    """Known response fields returned by `cm/get_network_settings`."""

    network_settings: NetworkSettings


class MobileNamespace:
    """Read-only helpers for live-verified mobile-network methods."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def cell_info(self) -> CellInfo:
        """Return basic cellular mode/operator and signal-level information."""

        return cast(CellInfo, self._client.call("cm", "get_cell_info"))

    def wan_info(self) -> CurrentWANInfo:
        """Return current WAN addressing and link/Internet status information."""

        return cast(CurrentWANInfo, self._client.call("cm", "get_current_wan_info"))

    def available_network_modes(self) -> AvailableNetworkModes:
        """Return the network modes reported as available by the router."""

        return cast(
            AvailableNetworkModes,
            self._client.call("cm", "get_available_network_mode"),
        )

    def network_settings(self) -> NetworkSettingsResponse:
        """Return the current mobile-network settings block."""

        return cast(
            NetworkSettingsResponse,
            self._client.call("cm", "get_network_settings"),
        )
