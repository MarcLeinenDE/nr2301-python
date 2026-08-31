# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os
import time

import pytest

from nr2301 import NR2301Client
from nr2301.exceptions import AuthenticationError, ProtocolError, TransportError

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical SIM provide-PIN test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )
if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical SIM provide-PIN test reboots the router and requires NR2301_DESTRUCTIVE_INTEGRATION=1",
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
        timeout=5.0,
    )
    router.login()
    return router


def _pin() -> str:
    value = os.environ.get("NR2301_SIM_PIN")
    if not value:
        pytest.skip("NR2301_SIM_PIN is required for this physical SIM test")
    if len(value) > 8:
        pytest.fail("NR2301_SIM_PIN exceeds the source-verified maximum length of 8")
    return value


def _state(router: NR2301Client) -> dict[str, int | str | None]:
    response = router.sim.status(timeout=4.0)
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


def _print_state(label: str, state: Mapping[str, object]) -> None:
    print(
        f"SIM_PIN_STATE {label} "
        f"enabled={state.get('pin_enabled')} "
        f"pin_status={state.get('pin_status')} "
        f"pin_attempts={state.get('pin_attempts')} "
        f"puk_attempts={state.get('puk_attempts')}"
    )


def _setting_response(response: Mapping[str, object]) -> tuple[object | None, str]:
    nested = response.get("response")
    if isinstance(nested, Mapping) and "setting_response" in nested:
        return nested.get("setting_response"), "response"
    if "setting_response" in response:
        return response.get("setting_response"), "top_level"
    return None, "missing"


def _recover_login(router: NR2301Client, *, attempts: int = 45, delay: float = 2.0) -> None:
    last_type = "none"
    for index in range(1, attempts + 1):
        try:
            router.login()
            print(f"ROUTER_RECOVERY login=OK attempt={index}")
            return
        except (TransportError, AuthenticationError, ProtocolError) as exc:
            last_type = type(exc).__name__
            time.sleep(delay)
    pytest.fail(
        f"router did not recover administrator login after reboot; last_exception_type={last_type}"
    )


def test_sim_provide_pin_after_reboot_and_restore() -> None:
    pin = _pin()
    router = _client()
    pin_protection_enabled = False
    recovered_after_reboot = False
    pin_ready_after_reboot = False

    try:
        initial = _state(router)
        _print_state("initial", initial)
        assert initial["sim_status"] == 1
        assert initial["pin_status"] == 5
        assert initial["pin_enabled"] == 0
        pin_attempts = int(initial["pin_attempts"])
        puk_attempts = int(initial["puk_attempts"])
        assert pin_attempts >= 2
        assert puk_attempts >= 2

        enable = router.sim.enable_pin(pin)
        enable_result, enable_shape = _setting_response(enable)
        print(
            f"SIM_PIN_ACTION action=enable_pin response_shape={enable_shape} "
            f"setting_response={enable_result}"
        )
        if enable_result != "OK":
            pytest.fail("enable_pin did not return setting_response=OK; reboot will not be attempted")
        pin_protection_enabled = True

        enabled = _state(router)
        _print_state("after_enable", enabled)
        assert enabled["pin_enabled"] == 1
        assert enabled["pin_attempts"] == pin_attempts
        assert enabled["puk_attempts"] == puk_attempts

        print("ROUTER_ACTION action=reboot")
        try:
            router.call("router", "router_call_reboot", timeout=5.0)
            print("ROUTER_ACTION reboot_call_returned=JSON")
        except (TransportError, ProtocolError) as exc:
            # A timeout/non-JSON response is expected evidence for a rebooting device.
            # Never print exception text: it may contain unnecessary transport details.
            print(f"ROUTER_ACTION reboot_call_interrupted exception_type={type(exc).__name__}")

        _recover_login(router)
        recovered_after_reboot = True

        locked = _state(router)
        _print_state("after_reboot", locked)
        assert locked["sim_status"] == 1
        assert locked["pin_enabled"] == 1
        assert locked["pin_attempts"] == pin_attempts
        assert locked["puk_attempts"] == puk_attempts

        if locked["pin_status"] != 2:
            pytest.fail(
                "router recovered but SIM did not report pin_status=2 (PIN required); "
                "provide_pin was intentionally NOT sent"
            )

        provide = router.sim.provide_pin(pin)
        provide_result, provide_shape = _setting_response(provide)
        print(
            f"SIM_PIN_ACTION action=provide_pin response_shape={provide_shape} "
            f"setting_response={provide_result}"
        )
        if provide_result != "OK":
            pytest.fail(
                "provide_pin did not return setting_response=OK; do not rerun before inspecting retry counters"
            )
        pin_ready_after_reboot = True

        ready = _state(router)
        _print_state("after_provide_pin", ready)
        assert ready["pin_status"] == 5
        assert ready["pin_enabled"] == 1
        assert ready["pin_attempts"] == pin_attempts
        assert ready["puk_attempts"] == puk_attempts

        disable = router.sim.disable_pin(pin)
        disable_result, disable_shape = _setting_response(disable)
        print(
            f"SIM_PIN_ACTION action=restore_disable_pin response_shape={disable_shape} "
            f"setting_response={disable_result}"
        )
        if disable_result != "OK":
            pytest.fail("disable_pin did not return setting_response=OK")
        pin_protection_enabled = False

        final = _state(router)
        _print_state("final", final)
        assert final["sim_status"] == initial["sim_status"]
        assert final["pin_status"] == initial["pin_status"]
        assert final["pin_enabled"] == initial["pin_enabled"]
        assert final["pin_attempts"] == pin_attempts
        assert final["puk_attempts"] == puk_attempts
    finally:
        # Conservative cleanup only after management recovery. If the reboot did
        # not recover, the user must inspect state manually instead of the test
        # sending credential operations blindly.
        if recovered_after_reboot and pin_protection_enabled:
            try:
                current = _state(router)
                _print_state("cleanup_observed", current)
                if current.get("pin_status") == 2 and not pin_ready_after_reboot:
                    # Exactly one known-correct PIN submission is permitted here.
                    response = router.sim.provide_pin(pin)
                    result, shape = _setting_response(response)
                    print(
                        f"SIM_PIN_CLEANUP action=provide_pin response_shape={shape} "
                        f"setting_response={result}"
                    )
                    if result == "OK":
                        pin_ready_after_reboot = True
                if pin_ready_after_reboot or current.get("pin_status") == 5:
                    response = router.sim.disable_pin(pin)
                    result, shape = _setting_response(response)
                    print(
                        f"SIM_PIN_CLEANUP action=disable_pin response_shape={shape} "
                        f"setting_response={result}"
                    )
            except Exception as exc:
                print(f"SIM_PIN_CLEANUP failed exception_type={type(exc).__name__}")

        router.close()
