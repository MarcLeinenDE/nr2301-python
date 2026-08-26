# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


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
