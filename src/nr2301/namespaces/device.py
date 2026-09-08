# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


_SLEEP_WAIT_MINUTES = (0, 10, 20, 30, 40, 60)


class DeviceInfo(TypedDict, total=False):
    ICCID: str
    IMEI: str
    IMSI: str
    MDN: str
    device_type: str
    domain: str
    lang_list: str
    platform: str
    result: int
    sn: str


class RuntimeInfo(TypedDict, total=False):
    boot_time: int
    cpu_temperature: int
    cpu_used_percentage: int
    memory_used_percentage: int
    result: int


class RouterDiagnostics(TypedDict, total=False):
    cpu_temp_normal: int
    cpu_usage_lv: int
    login_pwd_lv: int
    mem_usage_lv: int
    wan_st: int


class InternetDiagnostics(TypedDict, total=False):
    access: int
    result: int


class FeatureFlags(TypedDict, total=False):
    device_type: str
    local_update: int
    phonebook: int
    sdcard: int
    sms: int
    username: int
    ussd: int
    wds: int
    wifi_extender: int
    wizard: int


class FeatureList(TypedDict, total=False):
    features: FeatureFlags
    result: int


MacInfo = TypedDict(
    "MacInfo",
    {
        "5g_mac": str,
        "eth_mac": str,
        "extender_mac": str,
        "guest_mac": str,
        "result": int,
        "rndis_mac": str,
        "wifi_mac": str,
    },
    total=False,
)


class UILanguage(TypedDict, total=False):
    language: str
    result: int


class BatteryInfo(TypedDict, total=False):
    capacity: int
    ind: int
    status: int
    temperature: int


class SleepWaitTime(TypedDict, total=False):
    result: int


class DeviceNamespace:
    """Safe device/router status reads backed by normalized public contracts."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def info(self, *, timeout: float | None = None) -> DeviceInfo:
        """Return identity/platform information from `router/get_device_info`.

        The response can contain subscriber/device identifiers such as ICCID,
        IMSI and IMEI. Applications should treat those values as sensitive and
        avoid writing them to public logs by default.
        """

        return cast(
            DeviceInfo,
            self._client.call("router", "get_device_info", timeout=timeout),
        )

    def runtime(self, *, timeout: float | None = None) -> RuntimeInfo:
        """Return boot time, CPU temperature/load and memory usage."""

        return cast(
            RuntimeInfo,
            self._client.call("router", "get_runtime_info", timeout=timeout),
        )

    def diagnostics(self, *, timeout: float | None = None) -> RouterDiagnostics:
        """Return the router's live-verified diagnostic level values."""

        return cast(
            RouterDiagnostics,
            self._client.call("router", "get_diag_info", timeout=timeout),
        )

    def internet(self, *, timeout: float | None = None) -> InternetDiagnostics:
        """Return internet-access diagnostics (`access`: 1 available, 0 unavailable)."""

        return cast(
            InternetDiagnostics,
            self._client.call("router", "get_diag_internet_info", timeout=timeout),
        )

    def features(self, *, timeout: float | None = None) -> FeatureList:
        return cast(
            FeatureList,
            self._client.call("router", "get_feature_list", timeout=timeout),
        )

    def mac_info(self, *, timeout: float | None = None) -> MacInfo:
        """Return router interface MAC metadata.

        MAC addresses identify a concrete device/network and should not be
        copied into public fixtures or issue reports unless deliberately
        sanitized.
        """

        return cast(
            MacInfo,
            self._client.call("router", "get_mac_info", timeout=timeout),
        )

    def ui_language(self, *, timeout: float | None = None) -> UILanguage:
        return cast(
            UILanguage,
            self._client.call("router", "get_ui_language", timeout=timeout),
        )

    def set_ui_language(
        self,
        language: str,
        *,
        timeout: float | None = None,
    ) -> UILanguage:
        """Set one router-advertised UI language and require exact read-back.

        The stock frontend uses lowercase transport codes. Instead of freezing
        a firmware-specific list in the SDK, this helper validates the requested
        code against `router/get_device_info.lang_list` on the target router.
        Only the documented `language` field is written.
        """

        if not isinstance(language, str):
            raise TypeError("language must be a str")
        if not language:
            raise ValueError("language must not be empty")

        current = self.ui_language(timeout=timeout)
        current_code = self._ui_language_code(current)
        available = self._available_ui_languages(self.info(timeout=timeout))
        if language not in available:
            raise ValueError(
                "language must be one of the router-advertised codes: "
                + ", ".join(available)
            )
        if current_code == language:
            return current

        self._client.call(
            "router",
            "set_ui_language",
            data={"language": language},
            timeout=timeout,
        )

        verified = self.ui_language(timeout=timeout)
        actual = self._ui_language_code(verified)
        if actual != language:
            raise APIError(
                "router/set_ui_language could not be verified by exact read-back",
                method_id="router/set_ui_language",
                response={"expected": language, "actual": actual},
            )
        return verified

    def battery(self, *, timeout: float | None = None) -> BatteryInfo:
        """Return battery capacity/status and frontend-interpreted temperature in °C."""

        return cast(
            BatteryInfo,
            self._client.call("aoc", "get_bat_info", timeout=timeout),
        )

    def sleep_wait_time(self, *, timeout: float | None = None) -> SleepWaitTime:
        """Return the configured auto-sleep wait time.

        On the tested frontend, `result` is the minute value: 0, 10, 20, 30,
        40 or 60. Unknown values are preserved rather than normalized.
        """

        return cast(
            SleepWaitTime,
            self._client.call("aoc", "sleep_wait_time", timeout=timeout),
        )

    def set_sleep_wait_time(
        self,
        minutes: int,
        *,
        timeout: float | None = None,
    ) -> SleepWaitTime:
        """Set auto-sleep to a frontend-verified minute value and verify read-back.

        Supported values are 0 (off), 10, 20, 30, 40 and 60 minutes. A
        same-state call avoids an unnecessary write. The setter uses only the
        documented `time` field and accepts success only after the getter
        reports the requested value exactly.
        """

        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise TypeError("minutes must be an int")
        if minutes not in _SLEEP_WAIT_MINUTES:
            raise ValueError(
                "minutes must be one of 0, 10, 20, 30, 40 or 60"
            )

        current = self.sleep_wait_time(timeout=timeout)
        current_minutes = self._sleep_wait_minutes(current)
        if current_minutes == minutes:
            return current

        self._client.call(
            "aoc",
            "set_sleep_wait_time",
            data={"time": minutes},
            timeout=timeout,
        )

        verified = self.sleep_wait_time(timeout=timeout)
        actual = self._sleep_wait_minutes(verified)
        if actual != minutes:
            raise APIError(
                "aoc/set_sleep_wait_time could not be verified by exact read-back",
                method_id="aoc/set_sleep_wait_time",
                response={"expected": minutes, "actual": actual},
            )
        return verified

    @staticmethod
    def _ui_language_code(response: UILanguage) -> str:
        value: Any = response.get("language")
        if not isinstance(value, str) or not value:
            raise ProtocolError(
                "router/get_ui_language did not return a non-empty language string"
            )
        return value

    @staticmethod
    def _available_ui_languages(response: DeviceInfo) -> tuple[str, ...]:
        raw: Any = response.get("lang_list")
        if not isinstance(raw, str):
            raise ProtocolError(
                "router/get_device_info did not return a string lang_list"
            )
        values = tuple(part.strip() for part in raw.split(",") if part.strip())
        if not values:
            raise ProtocolError(
                "router/get_device_info returned an empty lang_list"
            )
        return values

    @staticmethod
    def _sleep_wait_minutes(response: SleepWaitTime) -> int:
        value: Any = response.get("result")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError("aoc/sleep_wait_time did not return an integer result")
        return value
