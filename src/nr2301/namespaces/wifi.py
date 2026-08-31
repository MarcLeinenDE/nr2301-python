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
WiFiMode = Literal[
    "DUAL",
    "DUAL GUEST",
    "2.4G 5G",
    "2.4G 5G GUEST",
]

WiFiSecurity = Literal[
    "psk-mixed+ccmp",
    "sae-mixed",
    "sae",
    "psk2+ccmp",
    "psk+ccmp",
    "psk2+tkip+ccmp",
    "psk+tkip+ccmp",
    "psk-mixed+tkip+ccmp",
    "psk2+tkip",
    "psk+tkip",
    "psk-mixed+tkip",
    "wep-mixed",
    "none",
]


_ALLOWED_AP_SECTIONS = {
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_DUAL",
    "wifi_if_GUEST",
    "wifi_timed_off",
}
_SECURITY_AP_SECTIONS = {
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_DUAL",
    "wifi_if_GUEST",
}
_VERIFIED_WIFI_ENCRYPTION_TOKENS = {
    "psk-mixed+ccmp",
    "sae-mixed",
    "sae",
    "psk2+ccmp",
    "psk+ccmp",
    "psk2+tkip+ccmp",
    "psk+tkip+ccmp",
    "psk-mixed+tkip+ccmp",
    "psk2+tkip",
    "psk+tkip",
    "psk-mixed+tkip",
    "wep-mixed",
    "none",
}
_VERIFIED_WIFI_MODES = {
    "DUAL",
    "DUAL GUEST",
    "2.4G 5G",
    "2.4G 5G GUEST",
}
_MODE_TRANSITION_BLOCKS = (
    "wifi_if_DUAL",
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_GUEST",
)
# ACIY.3 does not return an independent Guest isolate value. Only fields that
# can be read back safely are used for Guest-preservation verification.
_GUEST_VERIFY_FIELDS = (
    "band_mode",
    "ssid",
    "hidden",
    "encryption",
    "key",
    "maxassoc",
)

_WIFI_SECRET_FIELDS = {"ssid", "key", "password", "passphrase", "psk", "secret"}


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


class WPSActionWireless(TypedDict, total=False):
    wps_call_pbc_result: str
    wps_call_pin_result: str
    wps_call_cancel_result: str


class WPSActionResponse(TypedDict, total=False):
    wireless: WPSActionWireless


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
    """Wi-Fi helpers backed by normalized public NR2301 API evidence."""

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

    def call_wps_pbc(self, *, timeout: float | None = None) -> WPSActionResponse:
        """Start the live-verified WPS push-button action.

        This action does not auto-cancel. Consumers that only want to probe the
        capability should call :meth:`call_wps_cancel` immediately afterwards.
        """

        response = self._client.call(
            "wireless",
            "wifi_call_wps_pbc",
            timeout=timeout,
        )
        self._require_wps_action_ok(response, "wps_call_pbc_result")
        return cast(WPSActionResponse, response)

    def call_wps_pin(
        self,
        pin: str,
        *,
        timeout: float | None = None,
    ) -> WPSActionResponse:
        """Start the live-verified WPS PIN action using the supplied raw PIN.

        The shipped frontend contract sends ``wps_enable="1"`` together with
        ``wps_pin``. The SDK intentionally does not invent a stricter PIN format
        matrix than the evidence currently proves; firmware validation remains
        authoritative.
        """

        if not isinstance(pin, str) or not pin:
            raise ValueError("pin must be a non-empty string")
        response = self._client.call(
            "wireless",
            "wifi_call_wps_pin",
            data={"wps_enable": "1", "wps_pin": pin},
            timeout=timeout,
        )
        self._require_wps_action_ok(response, "wps_call_pin_result")
        return cast(WPSActionResponse, response)

    def call_wps_cancel(self, *, timeout: float | None = None) -> WPSActionResponse:
        """Cancel an active WPS PBC/PIN action and require the verified OK result."""

        response = self._client.call(
            "wireless",
            "wifi_call_wps_cancel",
            timeout=timeout,
        )
        self._require_wps_action_ok(response, "wps_call_cancel_result")
        return cast(WPSActionResponse, response)

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

    def guest_enabled(self, *, timeout: float | None = None) -> bool:
        """Return whether the verified `GUEST` token is present in Wi-Fi mode."""

        response = self.config(timeout=timeout)
        config = self._extract_config(response)
        _, guest = self._parse_verified_mode(self._extract_mode(config))
        return guest

    def uses_separate_ssids(self, *, timeout: float | None = None) -> bool:
        """Return True for the verified separate 2.4/5 GHz mode."""

        response = self.config(timeout=timeout)
        config = self._extract_config(response)
        separate, _ = self._parse_verified_mode(self._extract_mode(config))
        return separate

    def set_separate_ssids(
        self,
        separate: bool,
        *,
        write_timeout: float = 45.0,
        recovery_attempts: int = 34,
        recovery_delay: float = 3.0,
        recovery_timeout: float = 3.0,
    ) -> WiFiAPConfigResponse:
        """Switch between combined and separate 2.4/5 GHz main Wi-Fi modes.

        The current Guest state is preserved. All four current AP blocks that
        can participate in the transition are copied into the write payload,
        matching the previously live-verified application flow.

        `DUAL` is deliberately described as a combined/shared SSID mode rather
        than "Band Steering", because steering behavior was not separately
        proven by the reverse-engineering evidence.
        """

        if not isinstance(separate, bool):
            raise TypeError("separate must be a bool")
        self._validate_recovery_args(
            write_timeout,
            recovery_attempts,
            recovery_delay,
            recovery_timeout,
        )

        before = self.config()
        config = self._extract_config(before)
        current_mode = self._extract_mode(config)
        _, guest = self._parse_verified_mode(current_mode)
        wanted = "2.4G 5G" if separate else "DUAL"
        if guest:
            wanted += " GUEST"

        if current_mode == wanted:
            return before

        payload: dict[str, Any] = {"mode": wanted}
        for key in _MODE_TRANSITION_BLOCKS:
            block = config.get(key)
            if isinstance(block, Mapping):
                payload[key] = dict(block)

        expected_guest = self._guest_verifiable_fields(config.get("wifi_if_GUEST"))
        return self._write_config_and_verify_mode(
            payload,
            expected_mode=cast(WiFiMode, wanted),
            expected_guest=expected_guest,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def set_guest_enabled(
        self,
        enabled: bool,
        *,
        write_timeout: float = 45.0,
        recovery_attempts: int = 34,
        recovery_delay: float = 3.0,
        recovery_timeout: float = 3.0,
    ) -> WiFiAPConfigResponse:
        """Enable/disable Guest Wi-Fi by adding/removing the verified mode token.

        There is no separate Guest-enable field. The current Guest configuration
        is preserved and sent with the target mode. An independent Guest
        isolation control is intentionally not exposed because ACIY.3 does not
        round-trip that field in `wifi_get_ap_config`.
        """

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        self._validate_recovery_args(
            write_timeout,
            recovery_attempts,
            recovery_delay,
            recovery_timeout,
        )

        before = self.config()
        config = self._extract_config(before)
        current_mode = self._extract_mode(config)
        separate, guest = self._parse_verified_mode(current_mode)
        wanted = "2.4G 5G" if separate else "DUAL"
        if enabled:
            wanted += " GUEST"

        if guest == enabled:
            return before

        guest_block = config.get("wifi_if_GUEST")
        if not isinstance(guest_block, Mapping):
            raise ProtocolError(
                "wireless/wifi_get_ap_config did not return wifi_if_GUEST; "
                "refusing to toggle Guest without preserving its configuration"
            )

        payload = {
            "mode": wanted,
            "wifi_if_GUEST": dict(guest_block),
        }
        expected_guest = self._guest_verifiable_fields(guest_block)
        return self._write_config_and_verify_mode(
            payload,
            expected_mode=cast(WiFiMode, wanted),
            expected_guest=expected_guest,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

    def set_security(
        self,
        section: APSection,
        encryption: WiFiSecurity,
        key: str | None = None,
        *,
        write_timeout: float = 30.0,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> dict[str, Any]:
        """Set a live-verified Wi-Fi security token and optional key.

        All 13 source-known encryption tokens were physically accepted on
        24G, 5G, DUAL and Guest AP sections on ACIY.3. Protected modes require
        a non-empty key and verify both token and key through the existing
        AP-section read-back path.

        Open mode (``encryption="none"``) is intentionally special: ACIY.3
        accepts the open-mode token on all four sections, but 24G/5G/DUAL do
        not necessarily clear/read back ``key=""``. Therefore the SDK sends
        and verifies only the encryption token for open mode rather than
        inventing a universal empty-key invariant.

        Key length/format rules are deliberately not over-validated here: the
        public evidence proves token acceptance and representative synthetic
        keys, but not a complete per-security-mode key-format matrix. Firmware
        rejection remains authoritative.
        """

        if section not in _SECURITY_AP_SECTIONS:
            raise ValueError(f"unsupported Wi-Fi security section: {section!r}")
        if encryption not in _VERIFIED_WIFI_ENCRYPTION_TOKENS:
            raise ValueError(f"unsupported/unverified Wi-Fi encryption token: {encryption!r}")

        if encryption == "none":
            if key not in (None, ""):
                raise ValueError("open Wi-Fi mode does not accept a key argument")
            changes: dict[str, Any] = {"encryption": "none"}
        else:
            if not isinstance(key, str) or not key:
                raise ValueError("a non-empty key is required for protected Wi-Fi modes")
            changes = {"encryption": encryption, "key": key}

        return self.update_ap_section(
            section,
            changes,
            write_timeout=write_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )

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
            "expected_changes": self._redact_wifi_value(dict(changes)),
            "actual": self._redact_wifi_value(last_actual),
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

    def update_global_settings(
        self,
        changes: Mapping[str, Any],
        *,
        write_timeout: float = 30.0,
        recovery_attempts: int = 10,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
    ) -> WiFiAPConfigResponse:
        """Update evidenced top-level AP settings with recovery/read-back.

        Supported fields are currently `switch`, `maxassoc` and `power_level`.
        `mode` has dedicated state-machine helpers because it requires AP-block
        preservation.
        """

        allowed = {"switch", "maxassoc", "power_level"}
        if not isinstance(changes, Mapping) or not changes:
            raise ValueError("changes must be a non-empty mapping")
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported top-level Wi-Fi setting(s): {sorted(unknown)!r}")
        self._validate_recovery_args(
            write_timeout, recovery_attempts, recovery_delay, recovery_timeout
        )

        before = self.config()
        before_config = self._extract_config(before)
        if all(str(before_config.get(key)) == str(value) for key, value in changes.items()):
            return before

        write_error: NR2301Error | None = None
        try:
            self._client.call(
                "wireless",
                "wifi_set_ap_config",
                data=dict(changes),
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            write_error = exc

        last_actual: WiFiAPConfigResponse | None = None
        last_error: NR2301Error | None = None
        for attempt in range(recovery_attempts):
            try:
                actual = self.config(timeout=recovery_timeout)
                last_actual = actual
                config = self._extract_config(actual)
                if all(str(config.get(key)) == str(value) for key, value in changes.items()):
                    return actual
            except NR2301Error as exc:
                last_error = exc
                last_error = self._try_relogin(last_error)
            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "expected_changes": self._redact_wifi_value(dict(changes)),
            "actual": self._redact_wifi_value(last_actual),
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__
        raise APIError(
            "top-level Wi-Fi setting could not be verified by read-back",
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

    def _write_config_and_verify_mode(
        self,
        payload: Mapping[str, Any],
        *,
        expected_mode: WiFiMode,
        expected_guest: Mapping[str, Any],
        write_timeout: float,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> WiFiAPConfigResponse:
        write_error: NR2301Error | None = None
        try:
            self._client.call(
                "wireless",
                "wifi_set_ap_config",
                data=payload,
                timeout=write_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            # A management reset can destroy the write response even when the
            # router accepted the change. Read-back decides success.
            write_error = exc

        last_mode: str | None = None
        last_error: NR2301Error | None = None
        guest_preserved: bool | None = None

        for attempt in range(recovery_attempts):
            try:
                actual_response = self.config(timeout=recovery_timeout)
                actual_config = self._extract_config(actual_response)
                last_mode = self._extract_mode(actual_config)
                guest_preserved = self._guest_matches(
                    actual_config.get("wifi_if_GUEST"),
                    expected_guest,
                )
                if last_mode == expected_mode and guest_preserved:
                    return actual_response
            except NR2301Error as exc:
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "expected_mode": expected_mode,
            "actual_mode": last_mode,
            "guest_preserved": guest_preserved,
        }
        if write_error is not None:
            details["write_transport_error"] = type(write_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "Wi-Fi mode/Guest change could not be verified after recovery",
            method_id="wireless/wifi_set_ap_config",
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
    def _require_wps_action_ok(response: Mapping[str, Any], field: str) -> None:
        wireless = response.get("wireless")
        if not isinstance(wireless, Mapping) or wireless.get(field) != "OK":
            raise APIError(
                f"WPS action did not return {field}=OK",
                method_id="wireless/WPS_ACTION",
                response={"field": field, "result": wireless.get(field) if isinstance(wireless, Mapping) else None},
            )

    @staticmethod
    def _extract_config(response: Mapping[str, Any]) -> Mapping[str, Any]:
        config = response.get("config")
        if not isinstance(config, Mapping):
            raise ProtocolError("wireless/wifi_get_ap_config did not return a config object")
        return config

    @staticmethod
    def _extract_mode(config: Mapping[str, Any]) -> str:
        mode = config.get("mode")
        if not isinstance(mode, str) or not mode:
            raise ProtocolError("wireless/wifi_get_ap_config did not return a usable mode")
        return mode

    @staticmethod
    def _parse_verified_mode(mode: str) -> tuple[bool, bool]:
        if mode not in _VERIFIED_WIFI_MODES:
            raise ProtocolError(
                f"unsupported/unverified Wi-Fi mode {mode!r}; refusing to infer mode semantics"
            )
        return mode.startswith("2.4G 5G"), "GUEST" in mode.split()

    @staticmethod
    def _guest_verifiable_fields(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        return {key: value[key] for key in _GUEST_VERIFY_FIELDS if key in value}

    @staticmethod
    def _guest_matches(actual_value: Any, expected: Mapping[str, Any]) -> bool:
        if not expected:
            return True
        if not isinstance(actual_value, Mapping):
            return False
        for key, wanted in expected.items():
            actual = actual_value.get(key)
            if str(actual) != str(wanted):
                return False
        return True

    @staticmethod
    def _redact_wifi_value(value: Any, *, field: str | None = None) -> Any:
        if field is not None and field.lower() in _WIFI_SECRET_FIELDS:
            return "<redacted>"
        if isinstance(value, Mapping):
            return {
                str(key): WiFiNamespace._redact_wifi_value(item, field=str(key))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [WiFiNamespace._redact_wifi_value(item) for item in value]
        return value

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
