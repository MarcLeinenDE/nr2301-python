# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

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


class PortTriggerRule(TypedDict):
    index: int
    name: str
    trigger_port: str
    start_port: str
    end_port: str


class PortForwardRule(TypedDict):
    index: int
    name: str
    mac: str
    local_port: str
    wan_port: str


URLFilterMode = Literal["disable", "blacklist", "whitelist"]


class FirewallNamespace:
    """Firewall/NAT helpers backed by live-verified NR2301 contracts.

    Read helpers preserve raw firmware values. Write helpers use the exact wire
    shapes verified on firmware V1.00(ACIY.3)C0. They do not perform hidden
    read/restore transactions; callers that need transactional changes should
    read the current state first and verify/restore explicitly.

    DMZ destination clear/delete is intentionally not exposed because the
    stock NR2301 WebUI provides no verified clear/delete operation.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    # ---- reads ---------------------------------------------------------

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
        """Read the complete raw IP-filter list using the verified `all` selector."""

        return cast(
            FirewallRuleListResponse,
            self._client.call(
                "firewall",
                "ww_read_ip_filter",
                data={"ww_ip_filter": {"list": ["all"]}},
                timeout=timeout,
            ),
        )

    def port_filter(self, *, timeout: float | None = None) -> FirewallRuleListResponse:
        """Read the complete raw port-filter list using the verified `all` selector."""

        return cast(
            FirewallRuleListResponse,
            self._client.call(
                "firewall",
                "ww_read_port_filter",
                data={"ww_port_filter": {"list": ["all"]}},
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

    # ---- simple live-verified writes ----------------------------------

    def set_dmz_enabled(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Enable/disable DMZ without changing the stored destination."""

        return self._client.call(
            "firewall",
            "fw_set_disable_info",
            data={"dmz_disable": "0" if enabled else "1"},
            timeout=timeout,
        )

    def set_dmz_destination(
        self, destination: str, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Write a non-empty DMZ destination.

        Empty-string clear/delete is deliberately rejected because no such
        NR2301 WebUI contract has been verified.
        """

        if not destination.strip():
            raise ValueError("DMZ destination clear/delete is not a verified contract")
        return self._client.call(
            "firewall",
            "fw_edit_dmz_entry",
            data={"dmz_dest_ip": destination},
            timeout=timeout,
        )

    def set_vpn_passthrough(
        self,
        *,
        pptp: bool,
        l2tp: bool,
        ipsec: bool,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Set all VPN-passthrough flags using verified native JSON integers."""

        return self._client.call(
            "firewall",
            "fw_set_vpn_passthrough",
            data={"pptp": int(pptp), "l2tp": int(l2tp), "ipsec": int(ipsec)},
            timeout=timeout,
        )

    def set_ping_from_wan(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Set WAN-ping response using the live-verified nested WebUI body."""

        return self._client.call(
            "firewall",
            "set_ping_from_wan",
            data={
                "ping_from_wan": {
                    "ping_from_wan_enable": "1" if enabled else "0"
                }
            },
            timeout=timeout,
        )

    def set_admin_from_wan(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Set WAN administration using the live-verified nested WebUI body.

        The stock WebUI separately schedules `router/restart_web_server` after
        a changed value. This helper performs only the verified firewall setter
        and does not hide a disruptive restart action from the caller.
        """

        return self._client.call(
            "firewall",
            "set_admin_from_wan",
            data={
                "admin_from_wan": {
                    "admin_from_wan_enable": "1" if enabled else "0"
                }
            },
            timeout=timeout,
        )

    def set_upnp_enabled(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        return self._client.call(
            "firewall",
            "ww_upnp_open_close",
            data={"ww_upnp": {"upnp_enable": "1" if enabled else "0"}},
            timeout=timeout,
        )

    # ---- IP / port filter writes --------------------------------------

    def set_ip_filter_enabled(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        return self._client.call(
            "firewall",
            "ww_fw_set_disable_info",
            data={
                "ww_ip_filter": {
                    "ip_filter_disable": "0" if enabled else "1"
                }
            },
            timeout=timeout,
        )

    def replace_ip_filter_rules(
        self,
        rules: Sequence[str | None],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Replace the 10-slot IP-filter list.

        Sequence position is the rule index. `None`, empty string, and `"0"`
        represent an empty slot. Indices are serialized as strings to match
        the stock WebUI wire contract.
        """

        slots = _string_rule_slots(rules, value_key="ip")
        return self._client.call(
            "firewall",
            "ww_edit_ip_filter",
            data={"ww_ip_filter": {"list": slots}},
            timeout=timeout,
        )

    def set_port_filter_enabled(
        self, enabled: bool, *, timeout: float | None = None
    ) -> dict[str, Any]:
        return self._client.call(
            "firewall",
            "ww_fw_set_port_disable_info",
            data={
                "ww_port_filter": {
                    "port_filter_disable": "0" if enabled else "1"
                }
            },
            timeout=timeout,
        )

    def replace_port_filter_rules(
        self,
        rules: Sequence[str | None],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Replace the 10-slot port-filter list.

        Populated values use the raw verified `start:end` representation.
        Sequence position is the rule index; empty slots are string `"0"`.
        """

        slots = _string_rule_slots(rules, value_key="port")
        return self._client.call(
            "firewall",
            "ww_edit_port_filter",
            data={"ww_port_filter": {"list": slots}},
            timeout=timeout,
        )

    # ---- Port Trigger / Forward / URL filter --------------------------

    def set_port_trigger(
        self,
        enabled: bool,
        *,
        items: Sequence[Mapping[str, object]] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Write Port Trigger state with the verified WebUI semantics.

        When `enabled` is false the verified request is only `{\"enable\": 0}`;
        this disables triggering but does **not** delete stored items.

        When `enabled` is true, `items` is normalized to the complete 10-slot
        WebUI representation. To delete rules while preserving an ultimately
        disabled state, first call this method with `enabled=True` and the
        desired remaining items, verify read-back, then call it with
        `enabled=False`.
        """

        if not enabled:
            if items is not None:
                raise ValueError("items cannot be supplied when disabling Port Trigger")
            data: dict[str, object] = {"enable": 0}
        else:
            data = {"enable": 1, "items": _port_trigger_slots(items or ())}
        return self._client.call(
            "firewall", "set_port_trigger", data=data, timeout=timeout
        )

    def set_port_forward(
        self,
        enabled: bool,
        *,
        items: Sequence[Mapping[str, object]] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Write Port Forward state using the source/live-verified item shape."""

        if not enabled:
            if items is not None:
                raise ValueError("items cannot be supplied when disabling Port Forward")
            data: dict[str, object] = {"enable": 0}
        else:
            data = {"enable": 1, "items": _port_forward_slots(items or ())}
        return self._client.call(
            "firewall", "set_port_forward", data=data, timeout=timeout
        )

    def set_url_filter(
        self,
        mode: URLFilterMode,
        *,
        items: Sequence[str | None] = (),
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Set URL-filter mode and the active 10-slot item list.

        Disabled mode sends only `{\"mode\": \"disable\"}` and therefore does
        not imply stored item deletion. To clear stored blacklist/whitelist
        items, first write the corresponding active mode with an empty list,
        verify read-back, then disable if desired.
        """

        if mode == "disable":
            if items:
                raise ValueError("items cannot be supplied with disabled URL filter mode")
            data: dict[str, object] = {"mode": "disable"}
        elif mode in {"blacklist", "whitelist"}:
            key = "black_items" if mode == "blacklist" else "white_items"
            data = {"mode": mode, key: _url_filter_slots(items)}
        else:  # defensive runtime guard for untyped callers
            raise ValueError(f"unsupported URL filter mode: {mode!r}")
        return self._client.call(
            "firewall", "set_url_filter", data=data, timeout=timeout
        )


def _string_rule_slots(
    values: Sequence[str | None], *, value_key: str
) -> list[dict[str, str]]:
    if len(values) > 10:
        raise ValueError("NR2301 filter lists support at most 10 slots")
    slots: list[dict[str, str]] = []
    for index in range(10):
        raw = values[index] if index < len(values) else None
        text = "0" if raw is None or str(raw).strip() in {"", "0"} else str(raw)
        slots.append({value_key: text, "index": str(index)})
    return slots


def _port_trigger_slots(
    items: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = [
        {
            "index": index,
            "name": "",
            "trigger_port": "",
            "start_port": "",
            "end_port": "",
        }
        for index in range(10)
    ]
    _populate_indexed_slots(
        slots,
        items,
        fields=("name", "trigger_port", "start_port", "end_port"),
    )
    return slots


def _port_forward_slots(
    items: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = [
        {
            "index": index,
            "name": "",
            "mac": "",
            "local_port": "",
            "wan_port": "",
        }
        for index in range(10)
    ]
    _populate_indexed_slots(
        slots,
        items,
        fields=("name", "mac", "local_port", "wan_port"),
    )
    return slots


def _populate_indexed_slots(
    slots: list[dict[str, object]],
    items: Sequence[Mapping[str, object]],
    *,
    fields: Sequence[str],
) -> None:
    if len(items) > 10:
        raise ValueError("NR2301 rule lists support at most 10 slots")
    used: set[int] = set()
    for item in items:
        if "index" not in item:
            raise ValueError("rule item requires an index")
        try:
            index = int(item["index"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid rule index: {item['index']!r}") from exc
        if not 0 <= index < 10:
            raise ValueError("rule index must be between 0 and 9")
        if index in used:
            raise ValueError(f"duplicate rule index: {index}")
        used.add(index)
        slots[index] = {"index": index, **{field: str(item.get(field) or "") for field in fields}}


def _url_filter_slots(values: Sequence[str | None]) -> list[dict[str, object]]:
    if len(values) > 10:
        raise ValueError("NR2301 URL-filter lists support at most 10 slots")
    return [
        {
            "value": "" if index >= len(values) or values[index] is None else str(values[index]),
            "index": index,
        }
        for index in range(10)
    ]
