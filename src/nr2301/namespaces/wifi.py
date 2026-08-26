# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from ..exceptions import APIError, NR2301Error, ProtocolError, TransportError

if TYPE_CHECKING:
    from ..client import NR2301Client


APSection = Literal[
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_DUAL",
    "wifi_if_GUEST",
    "wifi_timed_off",
]

_ALLOWED_AP_SECTIONS = {
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_DUAL",
    "wifi_if_GUEST",
    "wifi_timed_off",
}


class WiFiAPConfig(TypedDict, total=False):
    """Known top-level fields from `wireless/wifi_get_ap_config.config`."""

    maxassoc: str
    mode: str
    password_modified: int
    power_level: str
    switch: str
    wifi_if_24G: dict[str, Any]
    wifi_if_5G: dict[str, Any]
    wifi_if_DUAL: dict[str, Any]
    wifi_if_GUEST: dict[str, Any]
    wifi_timed_off: dict[str, Any]


class WiFiAPConfigResponse(TypedDict, total=False):
    config: WiFiAPConfig
    result: int


class WiFiBasicInfo(TypedDict, total=False):
    switch: str


class WiFiTimedOffStatus(TypedDict, total=False):
    result: int
    status: str


class WiFiWPSState(TypedDict, total=False):
    wps_enable: str


class WiFiWPSResponse(TypedDict, total=False):
    wireless: WiFiWPSState


class WPSStatus(TypedDict, total=False):
    pbc_status: str


class WiFiDiagnostics(TypedDict, total=False):
    mode: str
    wifi_5g_pwd_lv: int
    wifi_dual_pwd_lv: int
    wifi_power: int
    wifi_pwd_lv: int
    wifi_st: int


class ExtenderConfig(TypedDict, total=False):
    enable: int
    key: str
    ssid: str


class ExtenderStatus(TypedDict, total=False):
    status: int


class WiFiNamespace:
    """Wi-Fi helpers backed by the public API v0.1.0 evidence."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def config(self, *, timeout: float | None = None) -> WiFiAPConfigResponse:
        """Return the complete live-verified AP configuration response."""

        response = self._client.call(
            "wireless",
            "wifi_get_ap_config",
            timeout=timeout,
        )
        self._extract_config(response)
        return cast(WiFiAPConfigResponse, response)

    def basic_info(self, *, timeout: float | None = None) -> WiFiBasicInfo:
        """Return the Wi-Fi master switch value using the frontend-shaped read."""

        return cast(
            WiFiBasicInfo,
            self._client.call(
                "wireless",
                "wifi_get_basic_info",
                data={"sw_only": "1"},
                timeout=timeout,
            ),
        )

    def timed_off_status(self, *, timeout: float | None = None) -> WiFiTimedOffStatus:
        return cast(
            WiFiTimedOffStatus,
            self._client.call(
                "wireless",
                "wifi_get_timed_off_status",
                timeout=timeout,
            ),
        )

    def wps(self, *, timeout: float | None = None) -> WiFiWPSResponse:
        response = self._client.call(
            "wireless",
            "wifi_get_wps_disable",
            timeout=timeout,
        )
        self._extract_wps_enable(response)
        return cast(WiFiWPSResponse, response)

    def wps_status(self, *, timeout: float | None = None) -> WPSStatus:
        return cast(
            WPSStatus,
            self._client.call("wireless", "wps_status", timeout=timeout),
        )

    def diagnostics(self, *, timeout: float | None = None) -> WiFiDiagnostics:
        return cast(
            WiFiDiagnostics,
            self._client.call("wireless", "get_diag_wifi_info", timeout=timeout),
        )

    def extender_config(self, *, timeout: float | None = None) -> ExtenderConfig:
        return cast(
            ExtenderConfig,
            self._client.call("wireless", "get_extender_config", timeout=timeout),
        )

    def extender_status(self, *, timeout: float | None = None) -> ExtenderStatus:
        return cast(
            ExtenderStatus,
            self._client.call("wireless", "get_extender_status", timeout=timeout),
        )

    def scan(self, *, timeout: float | None = None) -> dict[str, Any]:
        """Run the live-verified Wi-Fi scan without imposing an unstable schema."""

        return self._client.call("wireless", "wifi_scan", timeout=timeout)

    def update_ap_section(
        self,
        section: APSection,
        changes: Mapping[str, Any],
        *,
        write_timeout: float = 30.0,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> dict[str, Any]:
        """Update one existing AP block and require changed fields on read-back.

        The complete current section is copied first. Only the supplied fields
        are changed, then that full section is POSTed through
        `wireless/wifi_set_ap_config`.

        A Wi-Fi credential/SSID change can disconnect the host from the router.
        The SDK can retry HTTP/re-authentication, but it cannot reconnect the
        operating system to a newly named or newly keyed Wi-Fi network.
        """

        if section not in _ALLOWED_AP_SECTIONS:
            raise ValueError(f"unsupported Wi-Fi AP section: {section!r}")
        if not isinstance(changes, Mapping) or not changes:
            raise ValueError("changes must be a non-empty mapping")
        self._validate_recovery_args(
            write_timeout,
            recovery_attempts,
            recovery_delay,
            recovery_timeout,
        )

        before_response = self.config()
        before_config = self._extract_config(before_response)
        current = before_config.get(section)
        if not isinstance(current, Mapping):
            raise ProtocolError(
                f"wireless/wifi_get_ap_config did not return section {section!r}"
            )

        expected_block: dict[str, Any] = dict(current)
        expected_block.update(dict(changes))

        if all(current.get(key) == value for key, value in changes.items()):
            return dict(current)

        write_error: NR2301Error | None = None
        try:
            self._client.call(
                "wireless",
                "wifi_set_ap_config",
                data={section: expected_block},
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_actual: dict[str, Any] | None = None
        last_error: NR2301Error | None = None

        for attempt in range(recovery_attempts):
            try:
                actual_response = self.config(timeout=recovery_timeout)
                actual_config = self._extract_config(actual_response)
                actual_section = actual_config.get(section)
                if not isinstance(actual_section, Mapping):
                    raise ProtocolError(
                        f"wireless/wifi_get_ap_config did not return section {section!r}"
                    )
                last_actual = dict(actual_section)
                if all(last_actual.get(key) == value for key, value in changes.items()):
                    return last_actual
            except NR2301Error as exc:
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "section": section,
            "expected_changes": dict(changes),
            "actual": last_actual,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "Wi-Fi AP write could not be verified by read-back; the router may "
            "still be recovering or the management host may need to reconnect "
            "to the changed Wi-Fi network",
            method_id="wireless/wifi_set_ap_config",
            response=details,
        )

    def set_wps_enabled(
        self,
        enabled: bool,
        *,
        write_timeout: float = 30.0,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> WiFiWPSResponse:
        """Enable/disable WPS and require exact `wps_enable` read-back."""

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        self._validate_recovery_args(
            write_timeout,
            recovery_attempts,
            recovery_delay,
            recovery_timeout,
        )

        expected = "1" if enabled else "0"
        before = self.wps()
        if self._extract_wps_enable(before) == expected:
            return before

        write_error: NR2301Error | None = None
        try:
            self._client.call(
                "wireless",
                "wifi_set_wps_disable",
                data={"wps_enable": expected},
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_actual: WiFiWPSResponse | None = None
        last_error: NR2301Error | None = None

        for attempt in range(recovery_attempts):
            try:
                actual = self.wps(timeout=recovery_timeout)
                last_actual = actual
                if self._extract_wps_enable(actual) == expected:
                    return actual
            except NR2301Error as exc:
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "expected_wps_enable": expected,
            "actual": last_actual,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "WPS setting could not be verified by read-back",
            method_id="wireless/wifi_set_wps_disable",
            response=details,
        )

    def _try_relogin(self, previous_error: NR2301Error) -> NR2301Error:
        if self._client.password is None:
            return previous_error
        try:
            self._client.login()
        except NR2301Error as login_exc:
            return login_exc
        return previous_error

    @staticmethod
    def _extract_config(response: Mapping[str, Any]) -> Mapping[str, Any]:
        config = response.get("config")
        if not isinstance(config, Mapping):
            raise ProtocolError("wireless/wifi_get_ap_config did not return a config object")
        return config

    @staticmethod
    def _extract_wps_enable(response: Mapping[str, Any]) -> str:
        wireless = response.get("wireless")
        if not isinstance(wireless, Mapping):
            raise ProtocolError(
                "wireless/wifi_get_wps_disable did not return a wireless object"
            )
        value = wireless.get("wps_enable")
        if not isinstance(value, str):
            raise ProtocolError(
                "wireless/wifi_get_wps_disable returned invalid wps_enable"
            )
        return value

    @staticmethod
    def _validate_recovery_args(
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
