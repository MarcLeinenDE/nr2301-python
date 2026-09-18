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


class WANSettingsResponse(TypedDict, total=False):
    """Known response fields returned by `cm/get_wan_settings`."""

    mobile_ping_enable: int
    ping_address: str
    static: dict[str, str]
    wan_type_primary: str
    wifi_extender: dict[str, str]


class NetworkSelectMode(TypedDict, total=False):
    """Known response fields returned by `util_wan/get_network_select_mode`."""

    nw_sel_mode: str
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

    def wan_info(
        self,
        *,
        timeout: float | None = None,
    ) -> CurrentWANInfo:
        """Return current WAN addressing and link/Internet status information."""

        return cast(
            CurrentWANInfo,
            self._client.call("cm", "get_current_wan_info", timeout=timeout),
        )

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

    def wan_settings(
        self,
        *,
        timeout: float | None = None,
    ) -> WANSettingsResponse:
        """Return the raw primary-WAN/extender settings.

        The nested Wi-Fi extender block may contain a password. Treat this
        response as sensitive configuration data rather than routine telemetry.
        """

        return cast(
            WANSettingsResponse,
            self._client.call("cm", "get_wan_settings", timeout=timeout),
        )

    def search_networks(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Run the live-verified operator scan and return its raw network list."""

        return cast(
            dict[str, Any],
            self._client.call("util_wan", "search_network", timeout=timeout),
        )

    def network_select_mode(
        self,
        *,
        timeout: float | None = None,
    ) -> NetworkSelectMode:
        """Return the raw automatic/manual WAN network-selection mode."""

        return cast(
            NetworkSelectMode,
            self._client.call(
                "util_wan",
                "get_network_select_mode",
                timeout=timeout,
            ),
        )

    def disconnect_mobile(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Invoke the live-verified body-less mobile-WAN disconnect action.

        This operation can interrupt WAN and management connectivity. Callers
        that need recovery/read-back should prefer `reconnect_mobile()`.
        """

        return cast(
            dict[str, Any],
            self._client.call("cm", "disconnect", timeout=timeout),
        )

    def connect_mobile(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Invoke the live-verified body-less mobile-WAN connect action."""

        return cast(
            dict[str, Any],
            self._client.call("cm", "connect", timeout=timeout),
        )

    def reconnect_mobile(
        self,
        *,
        action_timeout: float = 10.0,
        recovery_attempts: int = 20,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> CurrentWANInfo:
        """Disconnect then reconnect mobile WAN and require connected read-back.

        A dropped HTTP response is treated as inconclusive. The helper attempts
        re-authentication/recovery and accepts success only after
        `cm/get_current_wan_info` reports at least one connected context.
        """

        self._validate_recovery_options(
            action_timeout=action_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

        try:
            self.disconnect_mobile(timeout=action_timeout)
        except (TransportError, ProtocolError):
            pass

        if recovery_delay:
            time.sleep(recovery_delay)

        try:
            self._ensure_session(recovery_timeout)
            self.connect_mobile(timeout=action_timeout)
        except (TransportError, ProtocolError):
            pass

        return self._wait_for_wan_connection(
            expected_connected=True,
            method_id="cm/connect",
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def select_network(
        self,
        network_param: str,
        *,
        expected_mode: str | None = None,
        action_timeout: float = 30.0,
        recovery_attempts: int = 20,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> NetworkSelectMode:
        """Select a scan/frontend-supplied network parameter and verify recovery.

        `"auto"` is the physically verified automatic-selection token. Manual
        values must come from the operator scan/frontend contract; this helper
        deliberately does not synthesize PLMN/operator identifiers.

        If `expected_mode` is omitted for `network_param="auto"`, the helper
        requires `nw_sel_mode == "auto"`. For other parameters the raw
        post-recovery selection-mode response is returned unless the caller
        supplies an explicit expected mode.
        """

        if not isinstance(network_param, str):
            raise TypeError("network_param must be a str")
        if not network_param.strip():
            raise ValueError("network_param must not be empty")
        if expected_mode is not None:
            if not isinstance(expected_mode, str):
                raise TypeError("expected_mode must be a str or None")
            if not expected_mode:
                raise ValueError("expected_mode must not be empty")
        elif network_param == "auto":
            expected_mode = "auto"

        self._validate_recovery_options(
            action_timeout=action_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

        write_response: dict[str, Any] | None = None
        write_error: NR2301Error | None = None
        try:
            write_response = self._client.call(
                "util_wan",
                "select_network",
                data={"network_param": network_param},
                timeout=action_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_response: NetworkSelectMode | None = None
        last_error: NR2301Error | None = None
        for attempt in range(recovery_attempts):
            try:
                self._ensure_session(recovery_timeout)
                current = self.network_select_mode(timeout=recovery_timeout)
                last_response = current
                actual = current.get("nw_sel_mode")
                if not isinstance(actual, str) or not actual:
                    raise ProtocolError(
                        "util_wan/get_network_select_mode returned invalid nw_sel_mode"
                    )
                if expected_mode is None or actual == expected_mode:
                    return current
            except NR2301Error as exc:
                last_error = exc

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "network_param": network_param,
            "expected_mode": expected_mode,
            "actual_mode": (
                last_response.get("nw_sel_mode")
                if last_response is not None
                else None
            ),
            "write_response": write_response,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "network selection could not be verified after recovery",
            method_id="util_wan/select_network",
            response=details,
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

    def carrier_aggregation_info(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return raw CA diagnostics through the required normal-admin multicall."""

        return self._multicall_read_member("get_ca_info", timeout=timeout)

    def radio_metrics(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return raw detailed radio metrics through the required multicall."""

        return self._multicall_read_member("query_eng_info", timeout=timeout)

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

    def _multicall_read_member(
        self,
        method: str,
        *,
        timeout: float | None,
    ) -> dict[str, Any]:
        """Dispatch one normal-admin read that is authorized only via multicall."""

        payload = self._client.multicall(
            [{"path": "cm", "method": method}],
            timeout=timeout,
        )
        if not isinstance(payload, Mapping):
            raise ProtocolError(
                f"cm/{method} multicall returned {type(payload).__name__}, "
                "expected an object envelope"
            )

        responses = payload.get("responses")
        if not isinstance(responses, list) or len(responses) != 1:
            raise ProtocolError(
                f"cm/{method} multicall did not return exactly one response member"
            )

        member = responses[0]
        if not isinstance(member, Mapping):
            raise ProtocolError(
                f"cm/{method} multicall response member is not a JSON object"
            )
        return dict(member)

    def _wait_for_wan_connection(
        self,
        *,
        expected_connected: bool,
        method_id: str,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> CurrentWANInfo:
        last_info: CurrentWANInfo | None = None
        last_error: NR2301Error | None = None

        for attempt in range(recovery_attempts):
            try:
                self._ensure_session(recovery_timeout)
                info = self.wan_info(timeout=recovery_timeout)
                last_info = info
                if self._wan_connected(info) == expected_connected:
                    return info
            except NR2301Error as exc:
                last_error = exc

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "expected_connected": expected_connected,
            "actual_connected": (
                self._wan_connected(last_info) if last_info is not None else None
            ),
        }
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__
        raise APIError(
            "mobile WAN state could not be verified after recovery",
            method_id=method_id,
            response=details,
        )

    def _ensure_session(self, timeout: float) -> None:
        try:
            self.wan_info(timeout=timeout)
            return
        except NR2301Error:
            if self._client.password is None:
                raise
        self._client.login()

    @staticmethod
    def _wan_connected(response: Mapping[str, Any]) -> bool:
        contexts = response.get("contextlist")
        if not isinstance(contexts, list) or not contexts:
            raise ProtocolError(
                "cm/get_current_wan_info did not return a non-empty contextlist"
            )
        states: list[int] = []
        for item in contexts:
            if not isinstance(item, Mapping):
                raise ProtocolError(
                    "cm/get_current_wan_info returned a non-object context"
                )
            value = item.get("connection_status")
            if isinstance(value, bool):
                raise ProtocolError(
                    "cm/get_current_wan_info returned invalid connection_status"
                )
            try:
                numeric = int(value)
            except (TypeError, ValueError) as exc:
                raise ProtocolError(
                    "cm/get_current_wan_info returned invalid connection_status"
                ) from exc
            if numeric not in {0, 1}:
                raise ProtocolError(
                    "cm/get_current_wan_info returned unknown connection_status"
                )
            states.append(numeric)
        return any(state == 1 for state in states)

    @staticmethod
    def _validate_recovery_options(
        *,
        action_timeout: float,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> None:
        if action_timeout <= 0:
            raise ValueError("action_timeout must be greater than zero")
        if recovery_attempts <= 0:
            raise ValueError("recovery_attempts must be greater than zero")
        if recovery_delay < 0:
            raise ValueError("recovery_delay must not be negative")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than zero")

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
