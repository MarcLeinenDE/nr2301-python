# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical statistics write tests require NR2301_WRITE_INTEGRATION=1",
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


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        pytest.fail(f"{label} did not return an object")
    return value


def _mode(router) -> str:
    response = _mapping(router.statistics.filter_mode(timeout=10.0), "filter mode")
    value = response.get("mode")
    if value not in {"black", "white"}:
        pytest.fail(f"unsupported filter mode {value!r}")
    return str(value)


def _traffic_totals(router) -> tuple[int, ...]:
    response = _mapping(router.statistics.traffic(timeout=10.0), "traffic")
    stats = _mapping(response.get("statistics"), "traffic.statistics")
    names = (
        "total_duration",
        "total_rx_bytes",
        "total_tx_bytes",
        "total_rx_tx_bytes",
        "total_error_bytes",
    )
    values: list[int] = []
    for name in names:
        value = stats.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            pytest.fail(f"traffic.statistics.{name} was not an integer")
        if value < 0:
            pytest.fail(f"traffic.statistics.{name} was negative")
        values.append(value)
    return tuple(values)


def test_filter_mode_same_state_write_and_readback(router):
    original = _mode(router)

    response = _mapping(
        router.statistics.set_filter_mode(original, timeout=10.0),
        "statistics/set_black_white_mode",
    )
    if "result" in response:
        value = response["result"]
        if isinstance(value, bool) or not isinstance(value, int):
            pytest.fail("statistics/set_black_white_mode.result was not an integer")

    assert _mode(router) == original

    print(
        "STAT_FILTER_MODE_WRITE"
        f" mode={original}"
        " same_state=True"
        " readback=True",
        flush=True,
    )


def test_clear_traffic_counters_action(router):
    before = _traffic_totals(router)
    before_sum = sum(before)
    before_nonzero = any(value > 0 for value in before)

    response = _mapping(
        router.statistics.clear_traffic(timeout=10.0),
        "statistics/stat_clear_common_data",
    )
    statistics = _mapping(
        response.get("statistics"),
        "statistics/stat_clear_common_data.statistics",
    )
    assert statistics.get("setting_response") == "OK"

    after = _traffic_totals(router)
    after_sum = sum(after)

    # The router can immediately accumulate a small amount of new traffic
    # while we perform the verification GET. If historical counters existed,
    # a successful clear should nevertheless reduce the aggregate total.
    if before_sum > 0:
        assert after_sum < before_sum

    print(
        "STAT_TRAFFIC_CLEAR"
        " setting_response=OK"
        f" before_nonzero={before_nonzero}"
        f" reset_effect_observed={before_sum > 0 and after_sum < before_sum}"
        " raw_counter_values_logged=False",
        flush=True,
    )
