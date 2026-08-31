# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical SIM PIN change test requires NR2301_WRITE_INTEGRATION=1",
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


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for this physical SIM test")
    if len(value) > 8:
        pytest.fail(f"{name} exceeds the source-verified maximum length of 8")
    return value


def _pin_state(router: NR2301Client) -> dict[str, int | str | None]:
    response = router.sim.status()
    pin_puk = response.get("pin_puk", {})
    setting = response.get("response", {})
    return {
        "sim_status": pin_puk.get("sim_status"),
        "pin_status": pin_puk.get("pin_status"),
        "pin_enabled": pin_puk.get("pin_enabled"),
        "pin_attempts": pin_puk.get("pin_attempts"),
        "puk_attempts": pin_puk.get("puk_attempts"),
        "setting_response": setting.get("setting_response") if isinstance(setting, Mapping) else None,
    }


def _setting_response(response: Mapping[str, object]) -> tuple[object | None, str]:
    nested = response.get("response")
    if isinstance(nested, Mapping) and "setting_response" in nested:
        return nested.get("setting_response"), "response"
    if "setting_response" in response:
        return response.get("setting_response"), "top_level"
    return None, "missing"


def _print_state(label: str, state: Mapping[str, object]) -> None:
    print(
        f"SIM_PIN_STATE {label} "
        f"enabled={state.get('pin_enabled')} "
        f"pin_status={state.get('pin_status')} "
        f"pin_attempts={state.get('pin_attempts')} "
        f"puk_attempts={state.get('puk_attempts')}"
    )


def _require_same_retry_budget(state: Mapping[str, object], pin_attempts: int, puk_attempts: int) -> None:
    assert state.get("pin_attempts") == pin_attempts
    assert state.get("puk_attempts") == puk_attempts


def test_sim_pin_change_and_restore() -> None:
    original_pin = _secret("NR2301_SIM_PIN")
    temporary_pin = _secret("NR2301_SIM_TEST_PIN")
    if original_pin == temporary_pin:
        pytest.fail("NR2301_SIM_TEST_PIN must differ from NR2301_SIM_PIN")

    router = _client()
    active_pin = "original"
    pin_enabled = False
    try:
        initial = _pin_state(router)
        _print_state("initial", initial)
        assert initial["sim_status"] == 1
        assert initial["pin_status"] == 5
        assert initial["pin_enabled"] == 0
        pin_attempts = int(initial["pin_attempts"])
        puk_attempts = int(initial["puk_attempts"])
        assert pin_attempts >= 2
        assert puk_attempts >= 2

        enable_response = router.sim.enable_pin(original_pin)
        enable_result, enable_shape = _setting_response(enable_response)
        print(f"SIM_PIN_ACTION action=enable_pin response_shape={enable_shape} setting_response={enable_result}")
        if enable_result != "OK":
            pytest.fail("enable_pin did not return setting_response=OK; no PIN guessing will be attempted")
        enabled_state = _pin_state(router)
        _print_state("after_enable", enabled_state)
        assert enabled_state["pin_enabled"] == 1
        _require_same_retry_budget(enabled_state, pin_attempts, puk_attempts)
        pin_enabled = True

        change_response = router.sim.change_pin(original_pin, temporary_pin)
        change_result, change_shape = _setting_response(change_response)
        print(f"SIM_PIN_ACTION action=change_to_temporary response_shape={change_shape} setting_response={change_result}")
        if change_result != "OK":
            pytest.fail(
                "change_pin to temporary PIN did not return setting_response=OK; "
                "active PIN is intentionally treated as uncertain and no alternate PIN will be guessed"
            )
        active_pin = "temporary"
        changed_state = _pin_state(router)
        _print_state("after_change_to_temporary", changed_state)
        assert changed_state["pin_enabled"] == 1
        _require_same_retry_budget(changed_state, pin_attempts, puk_attempts)

        restore_response = router.sim.change_pin(temporary_pin, original_pin)
        restore_result, restore_shape = _setting_response(restore_response)
        print(f"SIM_PIN_ACTION action=restore_original_pin response_shape={restore_shape} setting_response={restore_result}")
        if restore_result != "OK":
            pytest.fail(
                "restoring the original PIN did not return setting_response=OK; "
                "do not rerun or try another PIN before inspecting the current SIM state"
            )
        active_pin = "original"
        restored_pin_state = _pin_state(router)
        _print_state("after_restore_original_pin", restored_pin_state)
        assert restored_pin_state["pin_enabled"] == 1
        _require_same_retry_budget(restored_pin_state, pin_attempts, puk_attempts)

        disable_response = router.sim.disable_pin(original_pin)
        disable_result, disable_shape = _setting_response(disable_response)
        print(f"SIM_PIN_ACTION action=restore_disable_pin response_shape={disable_shape} setting_response={disable_result}")
        if disable_result != "OK":
            pytest.fail("disable_pin did not return setting_response=OK")
        pin_enabled = False

        final = _pin_state(router)
        _print_state("final", final)
        assert final["sim_status"] == initial["sim_status"]
        assert final["pin_status"] == initial["pin_status"]
        assert final["pin_enabled"] == initial["pin_enabled"]
        _require_same_retry_budget(final, pin_attempts, puk_attempts)
    finally:
        # Cleanup is intentionally conservative: only use the PIN whose activation
        # was positively acknowledged. Never try both credentials on uncertainty.
        if active_pin == "temporary":
            try:
                response = router.sim.change_pin(temporary_pin, original_pin)
                result, shape = _setting_response(response)
                print(f"SIM_PIN_CLEANUP action=restore_original_pin response_shape={shape} setting_response={result}")
                if result == "OK":
                    active_pin = "original"
            except Exception as exc:
                print(f"SIM_PIN_CLEANUP restore_original_pin_failed exception_type={type(exc).__name__}")

        if pin_enabled and active_pin == "original":
            try:
                response = router.sim.disable_pin(original_pin)
                result, shape = _setting_response(response)
                print(f"SIM_PIN_CLEANUP action=disable_pin response_shape={shape} setting_response={result}")
            except Exception as exc:
                print(f"SIM_PIN_CLEANUP disable_pin_failed exception_type={type(exc).__name__}")

        router.close()
