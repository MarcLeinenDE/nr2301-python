# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ipaddress
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, NR2301Error, ProtocolError, TransportError

if TYPE_CHECKING:
    from ..client import NR2301Client


_REQUIRED_COMBINED_FIELDS = (
    "disabled",
    "lan_ip",
    "lan_netmask",
    "start",
    "end",
    "leasetime",
    "mtu",
    "dnsmode",
    "dns1",
    "dns2",
    "ipv6dns1",
    "ipv6dns2",
)


class DHCPSettings(TypedDict, total=False):
    """Known fields from `router/router_get_dhcp_settings_comb.dhcp`."""

    disabled: str
    lan_ip: str
    lan_netmask: str
    start: str
    end: str
    leasetime: str
    mtu: str
    dnsmode: str
    dns1: str
    dns2: str
    ipv6dns1: str
    ipv6dns2: str


class CombinedDHCPResponse(TypedDict, total=False):
    """Known response fields returned by `router_get_dhcp_settings_comb`."""

    dhcp: DHCPSettings


class LANAddress(TypedDict, total=False):
    """Known LAN address fields returned by `router_get_lan_ip`."""

    lan_ip: str
    lan_netmask: str


class LANAddressResponse(TypedDict, total=False):
    """Known response fields returned by `router_get_lan_ip`."""

    router: LANAddress


class DNSSettings(TypedDict):
    """Verified DNS subset of the combined DHCP settings object."""

    dnsmode: str
    dns1: str
    dns2: str
    ipv6dns1: str
    ipv6dns2: str


class LANNamespace:
    """LAN/DHCP/DNS helpers backed by the public API v0.1.0 evidence."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def settings(self, *, timeout: float | None = None) -> CombinedDHCPResponse:
        """Return the combined LAN/DHCP/DNS settings response."""

        response = self._client.call(
            "router",
            "router_get_dhcp_settings_comb",
            timeout=timeout,
        )
        self._extract_dhcp(response)
        return cast(CombinedDHCPResponse, response)

    def address(self, *, timeout: float | None = None) -> LANAddressResponse:
        """Return the router LAN IPv4 address and netmask."""

        return cast(
            LANAddressResponse,
            self._client.call("router", "router_get_lan_ip", timeout=timeout),
        )

    def dhcp(self, *, timeout: float | None = None) -> DHCPSettings:
        """Return a copy of the combined DHCP settings object."""

        response = self._client.call(
            "router",
            "router_get_dhcp_settings_comb",
            timeout=timeout,
        )
        return cast(DHCPSettings, dict(self._extract_dhcp(response)))

    def dns(self, *, timeout: float | None = None) -> DNSSettings:
        """Return the five DNS fields from the combined DHCP object."""

        dhcp = self.dhcp(timeout=timeout)
        values: dict[str, str] = {}
        for key in ("dnsmode", "dns1", "dns2", "ipv6dns1", "ipv6dns2"):
            value = dhcp.get(key)
            if not isinstance(value, str):
                raise ProtocolError(
                    f"router/router_get_dhcp_settings_comb returned invalid {key!r}"
                )
            values[key] = value
        return cast(DNSSettings, values)

    def set_dns(
        self,
        primary: str,
        secondary: str = "",
        *,
        ipv6_primary: str = "",
        ipv6_secondary: str = "",
        write_timeout: int = 30,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> DNSSettings:
        """Set manual upstream DNS resolvers and require exact read-back.

        The NR2301 combined DHCP setter can reset management connectivity.
        A lost write response is therefore treated as inconclusive: this helper
        still attempts recovery/read-back and only returns when the requested
        DNS state is observed.
        """

        _validate_ip(primary, version=4, field="primary")
        _validate_optional_ip(secondary, version=4, field="secondary")
        _validate_optional_ip(ipv6_primary, version=6, field="ipv6_primary")
        _validate_optional_ip(ipv6_secondary, version=6, field="ipv6_secondary")

        expected = DNSSettings(
            dnsmode="manual",
            dns1=primary,
            dns2=secondary,
            ipv6dns1=ipv6_primary,
            ipv6dns2=ipv6_secondary,
        )
        return self._set_dns_fields(
            expected,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def set_dns_auto(
        self,
        *,
        write_timeout: int = 30,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> DNSSettings:
        """Return DNS handling to automatic mode and require exact read-back."""

        expected = DNSSettings(
            dnsmode="auto",
            dns1="",
            dns2="",
            ipv6dns1="",
            ipv6dns2="",
        )
        return self._set_dns_fields(
            expected,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def _set_dns_fields(
        self,
        expected: DNSSettings,
        *,
        write_timeout: int,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> DNSSettings:
        if write_timeout <= 0:
            raise ValueError("write_timeout must be greater than zero")
        if recovery_attempts <= 0:
            raise ValueError("recovery_attempts must be greater than zero")
        if recovery_delay < 0:
            raise ValueError("recovery_delay must not be negative")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than zero")

        before = self.dhcp()
        missing = [key for key in _REQUIRED_COMBINED_FIELDS if key not in before]
        if missing:
            raise ProtocolError(
                "refusing combined DHCP write because the read-back object is "
                f"missing required fields: {', '.join(missing)}"
            )

        payload: dict[str, Any] = dict(before)
        payload.update(expected)

        write_error: NR2301Error | None = None
        try:
            self._client.multicall(
                [
                    {
                        "path": "router",
                        "method": "router_set_dhcp_settings_comb",
                        "data": payload,
                        "timeout": write_timeout,
                    }
                ],
                timeout=float(write_timeout),
            )
        except (TransportError, ProtocolError) as exc:
            # The documented write may reset management TCP. The write outcome
            # is therefore determined by read-back, not by transport success.
            write_error = exc

        last_actual: DNSSettings | None = None
        last_error: NR2301Error | None = None

        for attempt in range(recovery_attempts):
            try:
                actual = self.dns(timeout=recovery_timeout)
                last_actual = actual
                if actual == expected:
                    return actual
            except NR2301Error as exc:
                last_error = exc
                if self._client.password is not None:
                    try:
                        self._client.login()
                    except NR2301Error as login_exc:
                        last_error = login_exc

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "expected": dict(expected),
            "actual": dict(last_actual) if last_actual is not None else None,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "DNS write could not be verified by exact read-back; "
            "the router state may be unchanged or the management connection "
            "may still be recovering",
            method_id="router/router_set_dhcp_settings_comb",
            response=details,
        )

    @staticmethod
    def _extract_dhcp(response: Mapping[str, Any]) -> Mapping[str, Any]:
        dhcp = response.get("dhcp")
        if not isinstance(dhcp, Mapping):
            raise ProtocolError(
                "router/router_get_dhcp_settings_comb did not return a dhcp object"
            )
        return dhcp


def _validate_ip(value: str, *, version: int, field: str) -> None:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid IPv{version} address") from exc
    if parsed.version != version:
        raise ValueError(f"{field} must be a valid IPv{version} address")


def _validate_optional_ip(value: str, *, version: int, field: str) -> None:
    if value:
        _validate_ip(value, version=version, field=field)
