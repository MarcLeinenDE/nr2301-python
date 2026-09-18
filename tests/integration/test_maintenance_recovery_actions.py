# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical maintenance recovery tests require NR2301_DESTRUCTIVE_INTEGRATION=1",
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


def test_legacy_backup_action(router):
    before = router.device.runtime(timeout=5.0).get("boot_time")

    response = router.maintenance.backup_config(timeout=10.0)

    assert int(response.get("rc")) == 0
    after = router.device.runtime(timeout=5.0).get("boot_time")
    if isinstance(before, int) and isinstance(after, int):
        assert after >= before


def test_restart_web_server_recovers_without_full_router_reboot(router):
    result = router.maintenance.restart_web_server(
        action_timeout=10.0,
        recovery_attempts=60,
        recovery_delay=0.5,
        recovery_timeout=3.0,
        initial_delay=0.5,
    )

    print(
        "WEB_SERVER_RESTART"
        f" boot_before={result.get('boot_time_before')}"
        f" boot_after={result.get('boot_time_after')}"
        f" outage_observed={result.get('outage_observed')}"
        f" action_error={result.get('action_error')!r}",
        flush=True,
    )

    assert result["boot_time_after"] >= result["boot_time_before"]


def test_router_reboot_get_variant_and_recovery(router):
    result = router.maintenance.reboot(
        action_timeout=5.0,
        recovery_attempts=120,
        recovery_delay=1.0,
        recovery_timeout=3.0,
        initial_delay=1.0,
    )

    print(
        "ROUTER_REBOOT"
        f" boot_before={result.get('boot_time_before')}"
        f" boot_after={result.get('boot_time_after')}"
        f" outage_observed={result.get('outage_observed')}"
        f" action_error={result.get('action_error')!r}",
        flush=True,
    )

    assert result["boot_time_after"] < result["boot_time_before"]
