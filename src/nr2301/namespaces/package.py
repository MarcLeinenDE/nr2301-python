# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class PackageDataValue(TypedDict, total=False):
    package_data: int


class PackageDataPeriod(PackageDataValue, total=False):
    start_date: str


class PackageDataMonthly(PackageDataValue, total=False):
    bill_day: int


class PackageSettings(TypedDict, total=False):
    alarm_threshold: int
    data_used: int
    package_data_daily: PackageDataValue
    package_data_half_year: PackageDataPeriod
    package_data_monthly: PackageDataMonthly
    package_data_one_year: PackageDataPeriod
    package_data_three_months: PackageDataPeriod
    package_data_unlimited: PackageDataValue
    package_type: str


class PackageStatus(TypedDict, total=False):
    status: int


class PackageNamespace:
    """Data-package usage/status reads backed by normalized public contracts."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def settings(self, *, timeout: float | None = None) -> PackageSettings:
        """Return the raw configured package/usage settings.

        Values are preserved exactly as returned by `package/get_package_settings`.
        The SDK does not infer units or reinterpret `package_type` beyond the
        semantics documented by nr2301-api.
        """

        return cast(
            PackageSettings,
            self._client.call("package", "get_package_settings", timeout=timeout),
        )

    def status(self, *, timeout: float | None = None) -> PackageStatus:
        """Return the raw package alert/status value."""

        return cast(
            PackageStatus,
            self._client.call("package", "get_package_status", timeout=timeout),
        )
