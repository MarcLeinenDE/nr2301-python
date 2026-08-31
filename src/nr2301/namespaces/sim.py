# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

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
    """SIM status and PIN/PUK capabilities backed by public contracts.

    PIN/PUK values are secrets. Callers must not log them. Mutation helpers
    apply a retry-budget guard by default, while the generic client transport
    remains available for deliberately lower-level use.
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

    def provide_pin(
        self,
        pin: str,
        *,
        timeout: float | None = None,
        protect_retries: bool = True,
    ) -> dict[str, Any]:
        """Provide the current SIM PIN using the shipped-frontend payload.

        The PIN is never included in SDK-generated error metadata.
        """

        pin = self._validate_secret(pin, "PIN")
        if protect_retries:
            self._require_retry_budget("pin", timeout=timeout)
        return self._client.call(
            "sim",
            "provide_pin",
            data={"pin_puk": {"pin": pin}},
            timeout=timeout,
        )

    def enable_pin(
        self,
        pin: str,
        *,
        timeout: float | None = None,
        protect_retries: bool = True,
    ) -> dict[str, Any]:
        """Enable SIM PIN protection using the current PIN."""

        pin = self._validate_secret(pin, "PIN")
        if protect_retries:
            self._require_retry_budget("pin", timeout=timeout)
        return self._client.call(
            "sim",
            "enable_pin",
            data={"pin_puk": {"pin": pin}},
            timeout=timeout,
        )

    def disable_pin(
        self,
        pin: str,
        *,
        timeout: float | None = None,
        protect_retries: bool = True,
    ) -> dict[str, Any]:
        """Disable SIM PIN protection using the current PIN."""

        pin = self._validate_secret(pin, "PIN")
        if protect_retries:
            self._require_retry_budget("pin", timeout=timeout)
        return self._client.call(
            "sim",
            "disable_pin",
            data={"pin_puk": {"pin": pin}},
            timeout=timeout,
        )

    def change_pin(
        self,
        pin: str,
        new_pin: str,
        *,
        timeout: float | None = None,
        protect_retries: bool = True,
    ) -> dict[str, Any]:
        """Change the SIM PIN using the exact shipped-frontend payload."""

        pin = self._validate_secret(pin, "PIN")
        new_pin = self._validate_secret(new_pin, "new PIN")
        if protect_retries:
            self._require_retry_budget("pin", timeout=timeout)
        return self._client.call(
            "sim",
            "change_pin",
            data={"pin_puk": {"pin": pin, "new_pin": new_pin}},
            timeout=timeout,
        )

    def reset_pin_using_puk(
        self,
        puk: str,
        new_pin: str,
        *,
        timeout: float | None = None,
        protect_retries: bool = True,
    ) -> dict[str, Any]:
        """Reset a blocked PIN using PUK plus a new PIN.

        This is a recovery capability. Normal physical coverage must not
        intentionally exhaust PIN retries merely to reach this state.
        """

        puk = self._validate_secret(puk, "PUK")
        new_pin = self._validate_secret(new_pin, "new PIN")
        if protect_retries:
            self._require_retry_budget("puk", timeout=timeout)
        return self._client.call(
            "sim",
            "reset_pin_using_puk",
            data={"pin_puk": {"puk": puk, "new_pin": new_pin}},
            timeout=timeout,
        )

    def _require_retry_budget(
        self,
        kind: str,
        *,
        timeout: float | None = None,
    ) -> None:
        status = self.status(timeout=timeout)
        pin_puk = self._extract_pin_puk(status)
        field = "puk_attempts" if kind == "puk" else "pin_attempts"
        value = pin_puk.get(field)
        if isinstance(value, bool):
            value = None
        try:
            attempts = int(value) if value is not None else None
        except (TypeError, ValueError):
            attempts = None
        if attempts is None:
            raise APIError(
                f"refusing SIM {kind.upper()} mutation because {field} is unavailable",
                method_id="sim/retry_guard",
                response={"attempt_field": field, "attempts": None},
            )
        if attempts <= 1:
            raise APIError(
                f"refusing SIM {kind.upper()} mutation to preserve the final remaining attempt",
                method_id="sim/retry_guard",
                response={"attempt_field": field, "attempts": attempts},
            )

    @staticmethod
    def _validate_secret(value: str, label: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{label} must be a string")
        if not value:
            raise ValueError(f"{label} must not be empty")
        # maxlength=8 is the only exact input-length constraint recovered from
        # the shipped WebUI. Do not invent a stricter minimum here.
        if len(value) > 8:
            raise ValueError(f"{label} exceeds the source-verified maximum length of 8")
        return value

    @staticmethod
    def _extract_pin_puk(response: Mapping[str, Any]) -> Mapping[str, Any]:
        pin_puk = response.get("pin_puk")
        if not isinstance(pin_puk, Mapping):
            raise ProtocolError("sim/get_sim_status did not return a pin_puk object")
        return pin_puk
