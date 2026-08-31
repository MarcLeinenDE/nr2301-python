# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical SIM PIN test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


def _client() -> NR2301Client:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")
    router = NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
    )
    router.login()
    return router


def _pin_puk(router: NR2301Client) -> Mapping[str, Any]:
    status = router.sim.status()
    pin_puk = status.get("pin_puk")
    assert isinstance(pin_puk, Mapping), "SIM status did not contain pin_puk"
    return pin_puk


def _int_field(state: Mapping[str, Any], field: str) -> int:
    value = state.get(field)
    assert isinstance(value, int) and not isinstance(value, bool), f"{field} is not an integer"
    return value


def _setting_response_shape(response: Mapping[str, Any]) -> tuple[str, Any]:
    if "setting_response" in response:
        return "top_level", response.get("setting_response")
    nested = response.get("response")
    if isinstance(nested, Mapping):
        return "response", nested.get("setting_response")
    return "missing", None


def test_sim_pin_protection_toggle_and_restore() -> None:
    pin = os.environ.get("NR2301_SIM_PIN")
    if not pin:
        pytest.skip("NR2301_SIM_PIN is required; keep the real PIN local and out of logs")

    router = _client()
    original_enabled: int | None = None
    try:
        initial = _pin_puk(router)
        sim_status = _int_field(initial, "sim_status")
        pin_status = _int_field(initial, "pin_status")
        original_enabled = _int_field(initial, "pin_enabled")
        pin_attempts_before = _int_field(initial, "pin_attempts")
        puk_attempts_before = _int_field(initial, "puk_attempts")

        assert sim_status == 1, f"expected SIM present, got sim_status={sim_status}"
        assert pin_status == 5, f"expected ready SIM before toggle, got pin_status={pin_status}"
        assert original_enabled in (0, 1), f"unexpected pin_enabled={original_enabled}"
        assert pin_attempts_before >= 3, (
            "refusing first physical PIN toggle unless the full observed PIN retry budget is available; "
            f"pin_attempts={pin_attempts_before}"
        )

        print(
            "SIM_PIN_STATE "
            f"initial enabled={original_enabled} pin_status={pin_status} "
            f"pin_attempts={pin_attempts_before} puk_attempts={puk_attempts_before}"
        )

        target_enabled = 0 if original_enabled else 1
        if target_enabled:
            action = router.sim.enable_pin(pin)
            action_name = "enable_pin"
        else:
            action = router.sim.disable_pin(pin)
            action_name = "disable_pin"

        shape, setting_response = _setting_response_shape(action)
        print(
            f"SIM_PIN_ACTION action={action_name} response_shape={shape} "
            f"setting_response={setting_response}"
        )

        changed = _pin_puk(router)
        changed_enabled = _int_field(changed, "pin_enabled")
        changed_pin_status = _int_field(changed, "pin_status")
        changed_pin_attempts = _int_field(changed, "pin_attempts")
        changed_puk_attempts = _int_field(changed, "puk_attempts")
        print(
            "SIM_PIN_STATE "
            f"after_change enabled={changed_enabled} pin_status={changed_pin_status} "
            f"pin_attempts={changed_pin_attempts} puk_attempts={changed_puk_attempts}"
        )

        assert changed_enabled == target_enabled, (
            f"SIM PIN protection did not change to requested state {target_enabled}; "
            f"readback={changed_enabled}"
        )
        assert changed_pin_attempts >= 2, (
            "PIN retry budget fell below the safe continuation threshold; aborting before any extra exploration"
        )
    finally:
        if original_enabled in (0, 1):
            current = _pin_puk(router)
            current_enabled = _int_field(current, "pin_enabled")
            if current_enabled != original_enabled:
                if original_enabled:
                    restore = router.sim.enable_pin(pin)
                    restore_name = "enable_pin"
                else:
                    restore = router.sim.disable_pin(pin)
                    restore_name = "disable_pin"
                shape, setting_response = _setting_response_shape(restore)
                print(
                    f"SIM_PIN_ACTION action=restore_{restore_name} response_shape={shape} "
                    f"setting_response={setting_response}"
                )

            final = _pin_puk(router)
            final_enabled = _int_field(final, "pin_enabled")
            final_pin_status = _int_field(final, "pin_status")
            final_pin_attempts = _int_field(final, "pin_attempts")
            final_puk_attempts = _int_field(final, "puk_attempts")
            print(
                "SIM_PIN_STATE "
                f"final enabled={final_enabled} pin_status={final_pin_status} "
                f"pin_attempts={final_pin_attempts} puk_attempts={final_puk_attempts}"
            )
            assert final_enabled == original_enabled, (
                f"SIM PIN protection restore failed: expected {original_enabled}, got {final_enabled}"
            )
        router.close()
