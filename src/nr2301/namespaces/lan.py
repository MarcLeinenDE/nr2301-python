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


class StaticReservation(TypedDict):
    index: str
    mac: str
    ip: str


class StaticReservation(TypedDict):
    index: str
    mac: str
    ip: str


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

    def legacy_dhcp_settings(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return `router_get_dhcp_settings` through its verified multicall form.

        This older getter is distinct from `router_get_dhcp_settings_comb`.
        Preserve its complete response because the firmware exposes a slightly
        different DHCP field set.
        """

        payload = self._client.multicall(
            [{"path": "router", "method": "router_get_dhcp_settings"}],
            timeout=timeout,
        )
        if not isinstance(payload, Mapping):
            raise ProtocolError(
                "router/router_get_dhcp_settings multicall did not return an object"
            )
        responses = payload.get("responses")
        if not isinstance(responses, list) or len(responses) != 1:
            raise ProtocolError(
                "router/router_get_dhcp_settings multicall did not return exactly one member"
            )
        member = responses[0]
        if not isinstance(member, Mapping):
            raise ProtocolError(
                "router/router_get_dhcp_settings response member is not an object"
            )
        data = member.get("data")
        if not isinstance(data, Mapping):
            raise ProtocolError(
                "router/router_get_dhcp_settings response member has no data object"
            )
        return dict(data)

    def static_reservations(self, *, timeout: float | None = None) -> dict[str, Any]:
        """Return the raw DHCP static-reservation response.

        The upstream API marks `router_get_dhcp_static_ip` as live-verified but
        does not freeze a stable nested response schema. Preserve the complete
        firmware JSON object without inventing field names or normalizations.
        """

        return self._client.call(
            "router",
            "router_get_dhcp_static_ip",
            timeout=timeout,
        )

    def set_dhcp_settings(
        self,
        settings: Mapping[str, Any],
        *,
        write_timeout: int = 30,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> DHCPSettings:
        """Write the complete verified 12-field combined DHCP object.

        Start from `lan.dhcp()`, modify only intended fields, then pass the
        complete object here. Missing values are never invented.
        """

        payload = self._normalize_dhcp_payload(settings)
        self._validate_recovery_options(
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

        current = self.dhcp(timeout=recovery_timeout)
        return self._write_dhcp_payload(
            payload,
            current=current,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def static_reservation_list(
        self,
        *,
        timeout: float | None = None,
    ) -> list[StaticReservation]:
        """Return normalized static DHCP reservation items."""

        response = self.static_reservations(timeout=timeout)
        dhcp = response.get("dhcp")
        if not isinstance(dhcp, Mapping):
            raise ProtocolError(
                "router/router_get_dhcp_static_ip did not return a dhcp object"
            )
        raw = dhcp.get("data")
        if not isinstance(raw, list):
            raise ProtocolError(
                "router/router_get_dhcp_static_ip did not return dhcp.data as a list"
            )
        result: list[StaticReservation] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ProtocolError("static DHCP reservation is not an object")
            result.append(self._normalize_reservation(item))
        return result

    def set_static_reservations(
        self,
        reservations: list[Mapping[str, Any]],
        *,
        write_timeout: int = 30,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> list[StaticReservation]:
        """Replace the complete 10-slot static DHCP reservation table."""

        if not isinstance(reservations, list):
            raise TypeError("reservations must be a list")
        if len(reservations) > 10:
            raise ValueError("the stock frontend supports at most 10 reservations")
        self._validate_recovery_options(
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

        expected = [self._normalize_reservation(item) for item in reservations]
        indices = [item["index"] for item in expected]
        if len(indices) != len(set(indices)):
            raise ValueError("reservation indices must be unique")

        current = self.static_reservation_list(timeout=recovery_timeout)
        if self._reservation_cmp(current) == self._reservation_cmp(expected):
            return current

        write_error: NR2301Error | None = None
        try:
            self._client.multicall(
                [{
                    "path": "router",
                    "method": "router_set_dhcp_static_ip",
                    "data": {"data": expected},
                    "timeout": write_timeout,
                }],
                timeout=float(write_timeout),
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_actual: list[StaticReservation] | None = None
        last_error: NR2301Error | None = None
        for attempt in range(recovery_attempts):
            try:
                actual = self.static_reservation_list(timeout=recovery_timeout)
                last_actual = actual
                if self._reservation_cmp(actual) == self._reservation_cmp(expected):
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
            "expected_count": len(expected),
            "actual_count": len(last_actual) if last_actual is not None else None,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__
        raise APIError(
            "static DHCP reservation write could not be verified by read-back",
            method_id="router/router_set_dhcp_static_ip",
            response=details,
        )

    def set_address_legacy(
        self,
        lan_ip: str,
        lan_netmask: str,
        *,
        write_timeout: float = 30.0,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
        force: bool = False,
    ) -> LANAddressResponse:
        """Use the deprecated dedicated LAN-address setter and require read-back.

        `force=True` is intended for explicit transport verification when the
        caller wants to execute the setter even though the requested address
        already matches the current state.
        """

        _validate_ip(lan_ip, version=4, field="lan_ip")
        _validate_ip(lan_netmask, version=4, field="lan_netmask")
        self._validate_recovery_options(
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

        if not isinstance(force, bool):
            raise TypeError("force must be a bool")

        current = self.address(timeout=recovery_timeout)
        router = current.get("router")
        if (
            not force
            and isinstance(router, Mapping)
            and router.get("lan_ip") == lan_ip
            and router.get("lan_netmask") == lan_netmask
        ):
            return current

        write_error: NR2301Error | None = None
        try:
            self._client.call(
                "router",
                "router_set_lan_ip",
                data={"lan_ip": lan_ip, "lan_netmask": lan_netmask},
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_actual: LANAddressResponse | None = None
        last_error: NR2301Error | None = None
        for attempt in range(recovery_attempts):
            try:
                actual = self.address(timeout=recovery_timeout)
                last_actual = actual
                router = actual.get("router")
                if isinstance(router, Mapping) and router.get("lan_ip") == lan_ip and router.get("lan_netmask") == lan_netmask:
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
            "expected": {"lan_ip": lan_ip, "lan_netmask": lan_netmask},
            "actual": last_actual,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__
        raise APIError(
            "legacy LAN address write could not be verified by read-back",
            method_id="router/router_set_lan_ip",
            response=details,
        )

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
        before = self.dhcp()
        payload: dict[str, Any] = dict(before)
        payload.update(expected)
        normalized = self._normalize_dhcp_payload(payload)
        self._validate_recovery_options(
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )
        verified = self._write_dhcp_payload(
            normalized,
            current=before,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )
        return cast(
            DNSSettings,
            {
                key: verified[key]
                for key in ("dnsmode", "dns1", "dns2", "ipv6dns1", "ipv6dns2")
            },
        )

    def _write_dhcp_payload(
        self,
        payload: dict[str, str],
        *,
        current: Mapping[str, Any],
        write_timeout: int,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> DHCPSettings:
        current_cmp = {
            key: current.get(key) for key in _REQUIRED_COMBINED_FIELDS
        }
        if current_cmp == payload:
            return cast(DHCPSettings, dict(current))

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
            write_error = exc

        last_actual: DHCPSettings | None = None
        last_error: NR2301Error | None = None
        for attempt in range(recovery_attempts):
            try:
                actual = self.dhcp(timeout=recovery_timeout)
                last_actual = actual
                actual_cmp = {
                    key: actual.get(key) for key in _REQUIRED_COMBINED_FIELDS
                }
                if actual_cmp == payload:
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
            "expected": payload,
            "actual": (
                {
                    key: last_actual.get(key)
                    for key in _REQUIRED_COMBINED_FIELDS
                }
                if last_actual is not None
                else None
            ),
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "combined DHCP write could not be verified by exact read-back",
            method_id="router/router_set_dhcp_settings_comb",
            response=details,
        )

    @classmethod
    def _normalize_dhcp_payload(
        cls,
        settings: Mapping[str, Any],
    ) -> dict[str, str]:
        if not isinstance(settings, Mapping):
            raise TypeError("settings must be a mapping")

        missing = [key for key in _REQUIRED_COMBINED_FIELDS if key not in settings]
        if missing:
            raise ProtocolError(
                "refusing combined DHCP write because the read-back object is "
                "missing required fields: " + ", ".join(missing)
            )

        payload: dict[str, str] = {}
        for key in _REQUIRED_COMBINED_FIELDS:
            value = settings[key]
            if not isinstance(value, str):
                raise TypeError(f"{key} must be a str")
            payload[key] = value

        cls._validate_dhcp_payload(payload)
        return payload

    @staticmethod
    def _validate_dhcp_payload(payload: Mapping[str, str]) -> None:
        if payload["disabled"] not in {"0", "1"}:
            raise ValueError("disabled must be '0' or '1'")

        for field in ("lan_ip", "start", "end"):
            _validate_ip(payload[field], version=4, field=field)

        try:
            ipaddress.IPv4Network(
                f"0.0.0.0/{payload['lan_netmask']}",
                strict=False,
            )
        except ValueError as exc:
            raise ValueError("lan_netmask must be a valid IPv4 netmask") from exc

        try:
            lease = int(payload["leasetime"])
        except ValueError as exc:
            raise ValueError("leasetime must be an integer string") from exc
        if lease < 60 or lease > 604800:
            raise ValueError("leasetime must be between 60 and 604800 seconds")

        try:
            mtu = int(payload["mtu"])
        except ValueError as exc:
            raise ValueError("mtu must be an integer string") from exc
        if mtu < 1280 or mtu > 1500:
            raise ValueError("mtu must be between 1280 and 1500")

        if payload["dnsmode"] not in {"auto", "manual"}:
            raise ValueError("dnsmode must be 'auto' or 'manual'")

        _validate_optional_ip(payload["dns1"], version=4, field="dns1")
        _validate_optional_ip(payload["dns2"], version=4, field="dns2")
        _validate_optional_ip(payload["ipv6dns1"], version=6, field="ipv6dns1")
        _validate_optional_ip(payload["ipv6dns2"], version=6, field="ipv6dns2")

    @staticmethod
    def _normalize_reservation(item: Mapping[str, Any]) -> StaticReservation:
        raw_index = item.get("index")
        if isinstance(raw_index, bool):
            raise TypeError("reservation index must be a string or integer")
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ValueError("reservation index must be numeric") from exc
        if index < 0 or index > 9:
            raise ValueError("reservation index must be between 0 and 9")

        mac = item.get("mac")
        if not isinstance(mac, str):
            raise TypeError("reservation mac must be a str")
        parts = mac.split(":")
        if (
            len(parts) != 6
            or any(
                len(part) != 2
                or any(ch not in "0123456789abcdefABCDEF" for ch in part)
                for part in parts
            )
        ):
            raise ValueError(
                "reservation mac must be a colon-separated MAC address"
            )

        ip = item.get("ip")
        if not isinstance(ip, str):
            raise TypeError("reservation ip must be a str")
        _validate_ip(ip, version=4, field="reservation ip")

        return StaticReservation(
            index=str(index),
            mac=mac.lower(),
            ip=str(ipaddress.ip_address(ip)),
        )

    @staticmethod
    def _reservation_cmp(
        items: list[StaticReservation],
    ) -> list[tuple[str, str, str]]:
        return sorted(
            (
                (item["index"], item["mac"].lower(), item["ip"])
                for item in items
            ),
            key=lambda value: int(value[0]),
        )

    @staticmethod
    def _validate_recovery_options(
        *,
        write_timeout: float,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> None:
        if write_timeout <= 0:
            raise ValueError("write_timeout must be greater than zero")
        if recovery_attempts <= 0:
            raise ValueError("recovery_attempts must be greater than zero")
        if recovery_delay < 0:
            raise ValueError("recovery_delay must not be negative")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than zero")

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
