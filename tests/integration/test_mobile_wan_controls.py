# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any

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


def _connection_statuses(info):
    contexts = info.get("contextlist")
    if not isinstance(contexts, list) or not contexts:
        pytest.fail("get_current_wan_info returned no contexts")

    statuses = []
    for item in contexts:
        if not isinstance(item, Mapping):
            pytest.fail("get_current_wan_info returned a non-object context")
        value = item.get("connection_status")
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            pytest.fail("get_current_wan_info returned invalid connection_status")
        if numeric not in {0, 1, 2}:
            pytest.fail(
                f"get_current_wan_info returned unknown connection_status={numeric}"
            )
        statuses.append(numeric)
    return statuses


def _internet_statuses(info):
    contexts = info.get("contextlist")
    if not isinstance(contexts, list):
        return []

    statuses = []
    for item in contexts:
        if not isinstance(item, Mapping):
            continue
        value = item.get("internet_status")
        try:
            statuses.append(int(value))
        except (TypeError, ValueError):
            continue
    return statuses


def _connected(info):
    statuses = _connection_statuses(info)
    if any(value == 1 for value in statuses):
        return True
    if any(value == 2 for value in statuses):
        return None
    return False


def _extract_rats(value: Any):
    rats = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "rat" and isinstance(child, str) and child:
                rats.add(child)
            rats.update(_extract_rats(child))
    elif isinstance(value, list):
        for child in value:
            rats.update(_extract_rats(child))
    return rats


def _trace_state(router, label, info):
    statuses = _connection_statuses(info)
    internet = _internet_statuses(info)

    data_mode = None
    cell_rats = set()
    eng_rats = set()

    try:
        cell = router.mobile.cell_info()
        basic = cell.get("celluar_basic_info")
        if isinstance(basic, Mapping):
            data_mode = basic.get("data_mode")
        cell_rats = _extract_rats(cell)
    except NR2301Error:
        pass

    # Query detailed engineering radio state only for the newly observed
    # transition state. This lets the physical run distinguish WAN transition
    # behavior from LTE+NR5G/NSA coexistence without overloading every poll.
    if 2 in statuses:
        try:
            eng_rats = _extract_rats(router.mobile.radio_metrics(timeout=3.0))
        except NR2301Error:
            pass

    print(
        "WAN_TRACE"
        f" label={label}"
        f" connection_status={statuses}"
        f" internet_status={internet}"
        f" data_mode={data_mode!r}"
        f" cell_rats={sorted(cell_rats)!r}"
        f" eng_rats={sorted(eng_rats)!r}",
        flush=True,
    )


def _recover(router, attempts=30, delay=0.25):
    last_error = None
    for _ in range(attempts):
        try:
            return router.mobile.wan_info(timeout=3.0)
        except NR2301Error as exc:
            last_error = exc
            try:
                router.login()
            except NR2301Error as login_exc:
                last_error = login_exc
        time.sleep(delay)
    raise AssertionError(
        f"router management did not recover: {type(last_error).__name__}"
    )


def _wait_final_state(
    router,
    expected=None,
    *,
    label,
    attempts=120,
    delay=0.25,
):
    last = None
    last_state = None

    for _ in range(attempts):
        try:
            last = _recover(router, attempts=4, delay=delay)
        except AssertionError:
            time.sleep(delay)
            continue

        state = _connected(last)
        last_state = state
        _trace_state(router, label, last)

        if state is not None and (expected is None or state is expected):
            return last, state

        time.sleep(delay)

    raise AssertionError(
        f"WAN connection state did not reach final expected={expected}; "
        f"last_state={last_state}"
    )


def _read_select_mode_with_recovery(router, attempts=30, delay=0.5):
    last_error = None
    for _ in range(attempts):
        try:
            return router.mobile.network_select_mode(timeout=5.0)
        except NR2301Error as exc:
            last_error = exc
            try:
                router.login()
            except NR2301Error as login_exc:
                last_error = login_exc
        time.sleep(delay)

    raise AssertionError(
        "network-select mode read did not recover: "
        f"{type(last_error).__name__}"
    )


def test_mobile_disconnect_connect_and_restore(router):
    initial, initial_connected = _wait_final_state(
        router,
        label="initial",
    )
    assert initial_connected in {True, False}
    boot_before = router.device.runtime().get("boot_time")

    try:
        try:
            router.mobile.disconnect_mobile(timeout=10.0)
        except NR2301Error:
            pass

        disconnected, state = _wait_final_state(
            router,
            False,
            label="after-disconnect",
        )
        assert state is False
        assert _connected(disconnected) is False

        try:
            router.mobile.connect_mobile(timeout=10.0)
        except NR2301Error:
            pass

        connected, state = _wait_final_state(
            router,
            True,
            label="after-connect",
        )
        assert state is True
        assert _connected(connected) is True

        reconnected = router.mobile.reconnect_mobile(
            action_timeout=10.0,
            recovery_attempts=120,
            recovery_delay=0.25,
            recovery_timeout=3.0,
        )
        assert _connected(reconnected) is True
        _trace_state(router, "production-reconnect-final", reconnected)

    finally:
        final, final_connected = _wait_final_state(
            router,
            label="pre-restore",
        )

        if initial_connected and not final_connected:
            try:
                router.mobile.connect_mobile(timeout=10.0)
            except NR2301Error:
                pass
            _wait_final_state(router, True, label="restore-connect")
        elif not initial_connected and final_connected:
            try:
                router.mobile.disconnect_mobile(timeout=10.0)
            except NR2301Error:
                pass
            _wait_final_state(router, False, label="restore-disconnect")

    restored, restored_state = _wait_final_state(
        router,
        initial_connected,
        label="restored",
    )
    assert restored_state is initial_connected
    assert _connected(restored) is initial_connected

    boot_after = router.device.runtime().get("boot_time")
    if isinstance(boot_before, int) and isinstance(boot_after, int):
        assert boot_after >= boot_before


def test_select_network_auto_with_exact_mode_restore(router):
    initial = _read_select_mode_with_recovery(router)
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
        recovery_attempts=60,
        recovery_delay=0.5,
        recovery_timeout=3.0,
    )
    assert selected.get("nw_sel_mode") == "auto"

    final = _read_select_mode_with_recovery(router)
    assert final.get("nw_sel_mode") == "auto"

    boot_after = router.device.runtime().get("boot_time")
    if isinstance(boot_before, int) and isinstance(boot_after, int):
        assert boot_after >= boot_before
