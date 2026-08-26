# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


class PinPukStatus(TypedDict, total=False):
    pin_attempts: int
    pin_enabled: int
    pin_status: int
    puk_attempts: int
    sim_status: int


class SIMSettingResponse(TypedDict, total=False):
    setting_response: str


class SIMStatusResponse(TypedDict, total=False):
    pin_puk: PinPukStatus
    response: SIMSettingResponse


class SIMStatusSummary(TypedDict, total=False):
    sim_status: int
    sim_status_text: str
    pin_status: int
    pin_status_text: str
    pin_enabled: int
    pin_enabled_text: str
    pin_attempts: int
    puk_attempts: int


_SIM_STATUS_TEXT = {
    0: "No SIM",
    1: "SIM present",
    2: "SIM error",
    3: "Unknown SIM error",
}
_PIN_STATUS_TEXT = {
    0: "PIN status unknown",
    1: "SIM detected",
    2: "PIN required",
    3: "PUK required",
    5: "Ready",
}
_PIN_ENABLED_TEXT = {
    0: "PIN protection disabled",
    1: "PIN protection enabled",
}


class SIMNamespace:
    """Safe SIM status reads.

    PIN/PUK mutations are intentionally not implemented because the public API
    classifies those paths as static-only / do-not-test-for-coverage.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def status(self, *, timeout: float | None = None) -> SIMStatusResponse:
        response = self._client.call("sim", "get_sim_status", timeout=timeout)
        self._extract_pin_puk(response)
        return cast(SIMStatusResponse, response)

    def summary(self, *, timeout: float | None = None) -> SIMStatusSummary:
        """Return a documented human-readable summary while preserving raw values."""

        response = self.status(timeout=timeout)
        pin_puk = self._extract_pin_puk(response)

        result: SIMStatusSummary = {}
        sim_status = pin_puk.get("sim_status")
        if isinstance(sim_status, int) and not isinstance(sim_status, bool):
            result["sim_status"] = sim_status
            result["sim_status_text"] = _SIM_STATUS_TEXT.get(
                sim_status, f"Unknown ({sim_status})"
            )

        pin_status = pin_puk.get("pin_status")
        if isinstance(pin_status, int) and not isinstance(pin_status, bool):
            result["pin_status"] = pin_status
            result["pin_status_text"] = _PIN_STATUS_TEXT.get(
                pin_status, f"Unknown ({pin_status})"
            )

        pin_enabled = pin_puk.get("pin_enabled")
        if isinstance(pin_enabled, int) and not isinstance(pin_enabled, bool):
            result["pin_enabled"] = pin_enabled
            result["pin_enabled_text"] = _PIN_ENABLED_TEXT.get(
                pin_enabled, f"Unknown ({pin_enabled})"
            )

        for field in ("pin_attempts", "puk_attempts"):
            value = pin_puk.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                result[field] = value  # type: ignore[literal-required]

        return result

    @staticmethod
    def _extract_pin_puk(response: Mapping[str, Any]) -> Mapping[str, Any]:
        pin_puk = response.get("pin_puk")
        if not isinstance(pin_puk, Mapping):
            raise ProtocolError("sim/get_sim_status did not return a pin_puk object")
        return pin_puk
