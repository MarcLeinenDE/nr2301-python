# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical WPS action test requires NR2301_WRITE_INTEGRATION=1",
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


def test_wps_pbc_pin_and_cancel_actions() -> None:
    router = _client()
    try:
        original = router.wifi.wps()
        original_enabled = str(original.get("wireless", {}).get("wps_enable")) == "1"
        if not original_enabled:
            router.wifi.set_wps_enabled(True, recovery_delay=0)
        try:
            def action_result(response: dict, field: str) -> tuple[str | None, str]:
                if field in response:
                    return response.get(field), "top_level"
                wireless = response.get("wireless")
                if isinstance(wireless, dict):
                    return wireless.get(field), "wireless"
                return None, "missing"

            pbc = router.wifi.call_wps_pbc()
            pbc_result, pbc_shape = action_result(pbc, "wps_call_pbc_result")
            print(f"WPS_ACTION_SHAPE pbc={pbc_shape} result={pbc_result}")
            assert pbc_result == "OK"

            cancel = router.wifi.call_wps_cancel()
            cancel_result, cancel_shape = action_result(cancel, "wps_call_cancel_result")
            print(f"WPS_ACTION_SHAPE cancel_after_pbc={cancel_shape} result={cancel_result}")
            assert cancel_result == "OK"

            pin = router.wifi.call_wps_pin("12345670")
            pin_result, pin_shape = action_result(pin, "wps_call_pin_result")
            print(f"WPS_ACTION_SHAPE pin={pin_shape} result={pin_result}")
            assert pin_result == "OK"

            cancel2 = router.wifi.call_wps_cancel()
            cancel2_result, cancel2_shape = action_result(cancel2, "wps_call_cancel_result")
            print(f"WPS_ACTION_SHAPE cancel_after_pin={cancel2_shape} result={cancel2_result}")
            assert cancel2_result == "OK"
        finally:
            current = router.wifi.wps()
            current_enabled = str(current.get("wireless", {}).get("wps_enable")) == "1"
            if current_enabled != original_enabled:
                router.wifi.set_wps_enabled(original_enabled, recovery_delay=0)
    finally:
        router.close()
