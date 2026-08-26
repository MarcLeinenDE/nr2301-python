# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, NR2301Error, ProtocolError, TransportError

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
    profile_mode: str
    profile: dict[str, Any]


class NetworkSettingsResponse(TypedDict, total=False):
    """Known response fields returned by `cm/get_network_settings`."""

    network_settings: NetworkSettings


class MobileNamespace:
    """Evidence-backed helpers for the NR2301 mobile-network API."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def cell_info(self) -> CellInfo:
        """Return basic cellular mode/operator and signal-level information."""

        return cast(CellInfo, self._client.call("cm", "get_cell_info"))

    def wan_info(self) -> CurrentWANInfo:
        """Return current WAN addressing and link/Internet status information."""

        return cast(CurrentWANInfo, self._client.call("cm", "get_current_wan_info"))

    def available_network_modes(
        self,
        *,
        timeout: float | None = None,
    ) -> AvailableNetworkModes:
        """Return the network modes reported as available by the router."""

        return cast(
            AvailableNetworkModes,
            self._client.call(
                "cm",
                "get_available_network_mode",
                timeout=timeout,
            ),
        )

    def network_settings(
        self,
        *,
        timeout: float | None = None,
    ) -> NetworkSettingsResponse:
        """Return the current mobile-network settings block."""

        return cast(
            NetworkSettingsResponse,
            self._client.call(
                "cm",
                "get_network_settings",
                timeout=timeout,
            ),
        )

    def set_network_mode(
        self,
        mode: str,
        *,
        write_timeout: float = 10.0,
        verify_attempts: int = 5,
        verify_delay: float = 1.0,
        verify_timeout: float = 3.0,
    ) -> NetworkSettings:
        """Set a router-reported network mode and require exact read-back.

        The public API deliberately does not define a universal hard-coded
        network-mode list. This helper therefore accepts only a value currently
        returned by `cm/get_available_network_mode` on the target router.
        """

        if not isinstance(mode, str) or not mode:
            raise ValueError("mode must be a non-empty string")
        self._validate_write_options(
            write_timeout=write_timeout,
            verify_attempts=verify_attempts,
            verify_delay=verify_delay,
            verify_timeout=verify_timeout,
        )

        available_response = self.available_network_modes(timeout=verify_timeout)
        available = available_response.get("network_modes")
        if not isinstance(available, list) or not all(
            isinstance(item, str) for item in available
        ):
            raise ProtocolError(
                "cm/get_available_network_mode did not return a string list"
            )
        if mode not in available:
            raise ValueError(
                f"network mode {mode!r} is not currently reported as available; "
                f"available modes: {available!r}"
            )

        current = self._read_network_settings(timeout=verify_timeout)
        current_mode = self._require_string_setting(current, "network_mode")
        if current_mode == mode:
            return current

        return self._set_string_setting(
            "network_mode",
            mode,
            write_timeout=write_timeout,
            verify_attempts=verify_attempts,
            verify_delay=verify_delay,
            verify_timeout=verify_timeout,
        )

    def set_data_roaming(
        self,
        enabled: bool,
        *,
        write_timeout: float = 10.0,
        verify_attempts: int = 5,
        verify_delay: float = 1.0,
        verify_timeout: float = 3.0,
    ) -> NetworkSettings:
        """Enable or disable mobile-data roaming and require exact read-back."""

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        self._validate_write_options(
            write_timeout=write_timeout,
            verify_attempts=verify_attempts,
            verify_delay=verify_delay,
            verify_timeout=verify_timeout,
        )

        expected = "1" if enabled else "0"
        current = self._read_network_settings(timeout=verify_timeout)
        current_value = self._require_string_setting(current, "data_roaming")
        if current_value == expected:
            return current

        return self._set_string_setting(
            "data_roaming",
            expected,
            write_timeout=write_timeout,
            verify_attempts=verify_attempts,
            verify_delay=verify_delay,
            verify_timeout=verify_timeout,
        )

    def _set_string_setting(
        self,
        field: str,
        expected: str,
        *,
        write_timeout: float,
        verify_attempts: int,
        verify_delay: float,
        verify_timeout: float,
    ) -> NetworkSettings:
        write_response: dict[str, Any] | None = None
        write_error: NR2301Error | None = None

        try:
            write_response = self._client.call(
                "cm",
                "set_network_settings",
                data={field: expected},
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            # A lost HTTP response is inconclusive. Determine the outcome from
            # the documented getter rather than assuming success or failure.
            write_error = exc

        last_settings: NetworkSettings | None = None
        last_error: NR2301Error | None = None

        for attempt in range(verify_attempts):
            try:
                settings = self._read_network_settings(timeout=verify_timeout)
                last_settings = settings
                actual = self._require_string_setting(settings, field)
                if actual == expected:
                    return settings
            except NR2301Error as exc:
                last_error = exc
                if self._client.password is not None:
                    try:
                        self._client.login()
                    except NR2301Error as login_exc:
                        last_error = login_exc

            if attempt + 1 < verify_attempts and verify_delay:
                time.sleep(verify_delay)

        details: dict[str, Any] = {
            "field": field,
            "expected": expected,
            "actual": (
                last_settings.get(field) if last_settings is not None else None
            ),
            "write_response": write_response,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_verification_error"] = type(last_error).__name__

        raise APIError(
            f"mobile setting {field!r} could not be verified by exact read-back",
            method_id="cm/set_network_settings",
            response=details,
        )

    def _read_network_settings(self, *, timeout: float) -> NetworkSettings:
        response = self.network_settings(timeout=timeout)
        settings = response.get("network_settings")
        if not isinstance(settings, Mapping):
            raise ProtocolError(
                "cm/get_network_settings did not return a network_settings object"
            )
        return cast(NetworkSettings, dict(settings))

    @staticmethod
    def _require_string_setting(settings: Mapping[str, Any], field: str) -> str:
        value = settings.get(field)
        if not isinstance(value, str):
            raise ProtocolError(
                f"cm/get_network_settings returned invalid {field!r}"
            )
        return value

    @staticmethod
    def _validate_write_options(
        *,
        write_timeout: float,
        verify_attempts: int,
        verify_delay: float,
        verify_timeout: float,
    ) -> None:
        if write_timeout <= 0:
            raise ValueError("write_timeout must be greater than zero")
        if verify_attempts <= 0:
            raise ValueError("verify_attempts must be greater than zero")
        if verify_delay < 0:
            raise ValueError("verify_delay must not be negative")
        if verify_timeout <= 0:
            raise ValueError("verify_timeout must be greater than zero")
