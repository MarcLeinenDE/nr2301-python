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
            pbc = router.wifi.call_wps_pbc()
            assert pbc.get("wireless", {}).get("wps_call_pbc_result") == "OK"
            cancel = router.wifi.call_wps_cancel()
            assert cancel.get("wireless", {}).get("wps_call_cancel_result") == "OK"

            pin = router.wifi.call_wps_pin("12345670")
            assert pin.get("wireless", {}).get("wps_call_pin_result") == "OK"
            cancel2 = router.wifi.call_wps_cancel()
            assert cancel2.get("wireless", {}).get("wps_call_cancel_result") == "OK"
        finally:
            current = router.wifi.wps()
            current_enabled = str(current.get("wireless", {}).get("wps_enable")) == "1"
            if current_enabled != original_enabled:
                router.wifi.set_wps_enabled(original_enabled, recovery_delay=0)
    finally:
        router.close()
