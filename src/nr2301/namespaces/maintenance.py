# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class TimedRebootSettings(TypedDict, total=False):
    enable: int
    repeat: int
    result: int
    time: str


class MaintenanceNamespace:
    """Evidence-backed router maintenance settings that are safe to read."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def timed_reboot(self, *, timeout: float | None = None) -> TimedRebootSettings:
        """Return the configured automatic reboot schedule."""

        return cast(
            TimedRebootSettings,
            self._client.call(
                "router",
                "router_get_timed_reboot",
                timeout=timeout,
            ),
        )

    def set_timed_reboot(
        self,
        enabled: bool,
        time: str,
        repeat: int,
        *,
        timeout: float | None = None,
    ) -> TimedRebootSettings:
        """Set the automatic reboot schedule and require exact read-back.

        `repeat` is the documented eight-bit mask: bits 0..6 are Sunday
        through Saturday and bit 7 represents no-repeat. The helper accepts
        only a normalized boolean enable state, an HH:MM time and a raw
        0..255 mask; it does not invent higher-level recurrence aliases.
        """

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        if not isinstance(time, str) or _TIME_RE.fullmatch(time) is None:
            raise ValueError("time must use 24-hour HH:MM format")
        if isinstance(repeat, bool) or not isinstance(repeat, int):
            raise TypeError("repeat must be an int")
        if not 0 <= repeat <= 0xFF:
            raise ValueError("repeat must be between 0 and 255")

        expected = {
            "enable": 1 if enabled else 0,
            "time": time,
            "repeat": repeat,
        }

        current = self.timed_reboot(timeout=timeout)
        current_fields = self._settings_fields(current)
        if current_fields == expected:
            return current

        self._client.call(
            "router",
            "router_set_timed_reboot",
            data=expected,
            timeout=timeout,
        )

        verified = self.timed_reboot(timeout=timeout)
        actual = self._settings_fields(verified)
        if actual != expected:
            raise APIError(
                "router/router_set_timed_reboot could not be verified by exact read-back",
                method_id="router/router_set_timed_reboot",
                response={"expected": expected, "actual": actual},
            )
        return verified

    @staticmethod
    def _settings_fields(response: TimedRebootSettings) -> dict[str, Any]:
        enable = response.get("enable")
        time = response.get("time")
        repeat = response.get("repeat")

        if isinstance(enable, bool) or not isinstance(enable, int):
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'enable'"
            )
        if not isinstance(time, str):
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'time'"
            )
        if isinstance(repeat, bool) or not isinstance(repeat, int):
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'repeat'"
            )

        return {"enable": enable, "time": time, "repeat": repeat}
