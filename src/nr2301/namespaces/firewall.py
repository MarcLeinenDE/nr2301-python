# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class FirewallValue(TypedDict, total=False):
    setting_response: str


class FirewallDisableInfo(FirewallValue, total=False):
    dmz_disable: str


class FirewallDMZInfo(FirewallValue, total=False):
    dmz_dest_ip: str


class FirewallWANAdminInfo(FirewallValue, total=False):
    admin_from_wan_enable: str


class FirewallWANPingInfo(FirewallValue, total=False):
    ping_from_wan_enable: str


class FirewallSwitchModeInfo(FirewallValue, total=False):
    default_policy: str
    ip_filter_disable: str


class FirewallSwitchPortModeInfo(FirewallValue, total=False):
    default_policy: str
    port_filter_disable: str


class FirewallUPnPInfo(FirewallValue, total=False):
    upnp_enable: str


class FirewallRuleListInfo(FirewallValue, total=False):
    list: list[object]


class FirewallEnvelope(TypedDict, total=False):
    firewall: FirewallValue


class FirewallVPNPassthrough(TypedDict, total=False):
    ipsec: int
    l2tp: int
    pptp: int
    result: int


class FirewallListSettings(TypedDict, total=False):
    enable: int
    items: list[object]


class FirewallListResponse(TypedDict, total=False):
    result: int
    settings: FirewallListSettings


class FirewallURLFilterSettings(TypedDict, total=False):
    black_items: list[object]
    mode: str
    white_items: list[object]


class FirewallURLFilterResponse(TypedDict, total=False):
    result: int
    settings: FirewallURLFilterSettings


class FirewallDisableResponse(TypedDict, total=False):
    firewall: FirewallDisableInfo


class FirewallDMZResponse(TypedDict, total=False):
    firewall: FirewallDMZInfo


class FirewallWANAdminResponse(TypedDict, total=False):
    firewall: FirewallWANAdminInfo


class FirewallWANPingResponse(TypedDict, total=False):
    firewall: FirewallWANPingInfo


class FirewallSwitchModeResponse(TypedDict, total=False):
    firewall: FirewallSwitchModeInfo


class FirewallSwitchPortModeResponse(TypedDict, total=False):
    firewall: FirewallSwitchPortModeInfo


class FirewallUPnPResponse(TypedDict, total=False):
    firewall: FirewallUPnPInfo


class FirewallRuleListResponse(TypedDict, total=False):
    firewall: FirewallRuleListInfo


class FirewallNamespace:
    """Read-only firewall/NAT state backed by live-verified public contracts.

    The first high-level firewall surface is deliberately read-only. It does
    not expose DMZ, WAN-management, forwarding, filtering or UPnP writes.
    Unknown/raw firmware values are returned without semantic remapping.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def disable_info(self, *, timeout: float | None = None) -> FirewallDisableResponse:
        return cast(
            FirewallDisableResponse,
            self._client.call("firewall", "fw_get_disable_info", timeout=timeout),
        )

    def dmz_info(self, *, timeout: float | None = None) -> FirewallDMZResponse:
        return cast(
            FirewallDMZResponse,
            self._client.call("firewall", "fw_get_dmz_info", timeout=timeout),
        )

    def vpn_passthrough(
        self, *, timeout: float | None = None
    ) -> FirewallVPNPassthrough:
        return cast(
            FirewallVPNPassthrough,
            self._client.call("firewall", "fw_get_vpn_passthrough", timeout=timeout),
        )

    def admin_from_wan(
        self, *, timeout: float | None = None
    ) -> FirewallWANAdminResponse:
        return cast(
            FirewallWANAdminResponse,
            self._client.call("firewall", "get_admin_from_wan", timeout=timeout),
        )

    def ping_from_wan(
        self, *, timeout: float | None = None
    ) -> FirewallWANPingResponse:
        return cast(
            FirewallWANPingResponse,
            self._client.call("firewall", "get_ping_from_wan", timeout=timeout),
        )

    def port_forward(self, *, timeout: float | None = None) -> FirewallListResponse:
        return cast(
            FirewallListResponse,
            self._client.call("firewall", "get_port_forward", timeout=timeout),
        )

    def port_trigger(self, *, timeout: float | None = None) -> FirewallListResponse:
        return cast(
            FirewallListResponse,
            self._client.call("firewall", "get_port_trigger", timeout=timeout),
        )

    def url_filter(
        self, *, timeout: float | None = None
    ) -> FirewallURLFilterResponse:
        return cast(
            FirewallURLFilterResponse,
            self._client.call("firewall", "get_url_filter", timeout=timeout),
        )

    def ip_filter(self, *, timeout: float | None = None) -> FirewallRuleListResponse:
        """Read the raw IP-filter list using the live-verified empty-list body."""

        return cast(
            FirewallRuleListResponse,
            self._client.call(
                "firewall",
                "ww_read_ip_filter",
                data={"ww_ip_filter": {"list": []}},
                timeout=timeout,
            ),
        )

    def port_filter(self, *, timeout: float | None = None) -> FirewallRuleListResponse:
        """Read the raw port-filter list using the live-verified empty-list body."""

        return cast(
            FirewallRuleListResponse,
            self._client.call(
                "firewall",
                "ww_read_port_filter",
                data={"ww_port_filter": {"list": []}},
                timeout=timeout,
            ),
        )

    def ip_filter_mode_state(
        self, *, timeout: float | None = None
    ) -> FirewallSwitchModeResponse:
        return cast(
            FirewallSwitchModeResponse,
            self._client.call("firewall", "ww_read_switch_mode_state", timeout=timeout),
        )

    def port_filter_mode_state(
        self, *, timeout: float | None = None
    ) -> FirewallSwitchPortModeResponse:
        return cast(
            FirewallSwitchPortModeResponse,
            self._client.call(
                "firewall", "ww_read_switch_port_mode_state", timeout=timeout
            ),
        )

    def upnp_state(self, *, timeout: float | None = None) -> FirewallUPnPResponse:
        return cast(
            FirewallUPnPResponse,
            self._client.call("firewall", "ww_upnp_open_close_state", timeout=timeout),
        )
