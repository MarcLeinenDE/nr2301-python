# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client, NR2301Error


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical disruptive WAN tests require NR2301_DESTRUCTIVE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        yield client


def _connected(info):
    contexts = info.get("contextlist")
    if not isinstance(contexts, list) or not contexts:
        pytest.fail("get_current_wan_info returned no contexts")
    states = []
    for item in contexts:
        if not isinstance(item, Mapping):
            pytest.fail("get_current_wan_info returned a non-object context")
        value = item.get("connection_status")
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            pytest.fail("get_current_wan_info returned invalid connection_status")
        if numeric not in {0, 1}:
            pytest.fail("get_current_wan_info returned unknown connection_status")
        states.append(numeric)
    return any(value == 1 for value in states)


def _recover(router, attempts=30, delay=1.0):
    last_error = None
    for _ in range(attempts):
        try:
            info = router.mobile.wan_info(timeout=3.0)
            return info
        except NR2301Error as exc:
            last_error = exc
            try:
                router.login()
            except NR2301Error as login_exc:
                last_error = login_exc
        time.sleep(delay)
    raise AssertionError(f"router management did not recover: {type(last_error).__name__}")


def _wait_connected(router, expected, attempts=30, delay=1.0):
    last = None
    for _ in range(attempts):
        last = _recover(router, attempts=1, delay=0)
        if _connected(last) is expected:
            return last
        time.sleep(delay)
    raise AssertionError(
        f"WAN connection state did not become {expected}; last={_connected(last)}"
    )


def test_mobile_disconnect_connect_and_restore(router):
    initial = _recover(router)
    initial_connected = _connected(initial)
    boot_before = router.device.runtime().get("boot_time")

    try:
        # Exercise the documented body-less disconnect action.
        try:
            router.mobile.disconnect_mobile(timeout=10.0)
        except NR2301Error:
            # Lost response is explicitly inconclusive for this disruptive call.
            pass

        disconnected = _wait_connected(router, False)
        assert _connected(disconnected) is False

        # Exercise the documented body-less connect action.
        try:
            router.mobile.connect_mobile(timeout=10.0)
        except NR2301Error:
            pass

        connected = _wait_connected(router, True)
        assert _connected(connected) is True

        # Exercise the combined production recovery helper as well.
        reconnected = router.mobile.reconnect_mobile(
            action_timeout=10.0,
            recovery_attempts=30,
            recovery_delay=1.0,
            recovery_timeout=3.0,
        )
        assert _connected(reconnected) is True

    finally:
        final = _recover(router)
        final_connected = _connected(final)
        if initial_connected and not final_connected:
            try:
                router.mobile.connect_mobile(timeout=10.0)
            except NR2301Error:
                pass
            _wait_connected(router, True)
        elif not initial_connected and final_connected:
            try:
                router.mobile.disconnect_mobile(timeout=10.0)
            except NR2301Error:
                pass
            _wait_connected(router, False)

    restored = _recover(router)
    assert _connected(restored) is initial_connected

    boot_after = router.device.runtime().get("boot_time")
    if isinstance(boot_before, int) and isinstance(boot_after, int):
        assert boot_after >= boot_before


def test_select_network_auto_with_exact_mode_restore(router):
    initial = router.mobile.network_select_mode(timeout=5.0)
    mode = initial.get("nw_sel_mode")
    if mode != "auto":
        pytest.skip(
            "network selection is not currently auto; exact manual network_param "
            "restore is not yet reconstructed"
        )

    boot_before = router.device.runtime().get("boot_time")

    selected = router.mobile.select_network(
        "auto",
        expected_mode="auto",
        action_timeout=30.0,
        recovery_attempts=30,
        recovery_delay=1.0,
        recovery_timeout=3.0,
    )
    assert selected.get("nw_sel_mode") == "auto"

    final = router.mobile.network_select_mode(timeout=5.0)
    assert final.get("nw_sel_mode") == "auto"

    boot_after = router.device.runtime().get("boot_time")
    if isinstance(boot_before, int) and isinstance(boot_after, int):
        assert boot_after >= boot_before
