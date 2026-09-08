# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


_TIME_RE = re.compile(r"^(?:[0-9]|1[0-9]|2[0-3]):(?:[0-9]|[0-5][0-9])$")


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
        """Return the configured automatic reboot schedule.

        The raw firmware time string is preserved. ACIY.3 has been observed
        returning an unpadded value such as ``0:0``; callers must therefore
        not assume that getter values are always textual ``HH:MM``.
        """

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
        """Set the automatic reboot schedule and require semantic read-back.

        ``repeat`` is the documented eight-bit mask: bits 0..6 are Sunday
        through Saturday and bit 7 represents no-repeat. Time input may use
        one- or two-digit hour/minute components because the live getter can
        return unpadded values; writes are normalized to zero-padded ``HH:MM``.
        """

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        canonical_time = self._canonical_time(time)
        if isinstance(repeat, bool) or not isinstance(repeat, int):
            raise TypeError("repeat must be an int")
        if not 0 <= repeat <= 0xFF:
            raise ValueError("repeat must be between 0 and 255")

        expected = {
            "enable": 1 if enabled else 0,
            "time": canonical_time,
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
                "router/router_set_timed_reboot could not be verified by semantic read-back",
                method_id="router/router_set_timed_reboot",
                response={"expected": expected, "actual": actual},
            )
        return verified

    @staticmethod
    def _canonical_time(value: str) -> str:
        if not isinstance(value, str) or _TIME_RE.fullmatch(value) is None:
            raise ValueError(
                "time must use a valid 24-hour H:M/HH:MM representation"
            )
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        return f"{hour:02d}:{minute:02d}"

    @classmethod
    def _settings_fields(cls, response: TimedRebootSettings) -> dict[str, Any]:
        enable = response.get("enable")
        time = response.get("time")
        repeat = response.get("repeat")

        if enable not in {0, 1} or isinstance(enable, bool):
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'enable'"
            )
        try:
            canonical_time = cls._canonical_time(time)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'time'"
            ) from exc
        if isinstance(repeat, bool) or not isinstance(repeat, int) or not 0 <= repeat <= 0xFF:
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'repeat'"
            )

        return {"enable": enable, "time": canonical_time, "repeat": repeat}
