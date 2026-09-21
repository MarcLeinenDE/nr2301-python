# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import os
import time

import pytest

from nr2301 import NR2301Client, NR2301Error


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical factory-reset tests require NR2301_DESTRUCTIVE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    factory_password = os.environ.get("NR2301_FACTORY_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required")
    if not factory_password:
        pytest.skip(
            "NR2301_FACTORY_PASSWORD is required; use the device-specific "
            "default admin password shown on the NR2301 LCD"
        )

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        yield client


def _stable_config_snapshot(router):
    readers = {
        "ui_language": lambda: router.device.ui_language(timeout=5.0),
        "work_mode": lambda: router.device.work_mode(timeout=5.0),
        "sleep_wait_time": lambda: router.device.sleep_wait_time(timeout=5.0),
        "timed_reboot": lambda: router.maintenance.timed_reboot(timeout=5.0),
        "dns": lambda: router.lan.dns(timeout=5.0),
        "upnp": lambda: router.firewall.upnp_state(timeout=5.0),
        "vpn_passthrough": lambda: router.firewall.vpn_passthrough(timeout=5.0),
        "ping_from_wan": lambda: router.firewall.ping_from_wan(timeout=5.0),
        "admin_from_wan": lambda: router.firewall.admin_from_wan(timeout=5.0),
    }

    result = {}
    for name, reader in readers.items():
        try:
            result[name] = reader()
        except NR2301Error as exc:
            setattr(exc, "_nr2301_snapshot_field", name)
            raise
    return result


def _snapshot_with_recovery(router, *, attempts=90, delay=1.0):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            snapshot = _stable_config_snapshot(router)
            if attempt > 1:
                print(
                    "FACTORY_CONFIG_API_READY"
                    f" attempt={attempt}"
                    f" previous_field={getattr(last_error, '_nr2301_snapshot_field', 'unknown') if last_error else None}"
                    f" previous_error={type(last_error).__name__ if last_error else None}",
                    flush=True,
                )
            return snapshot
        except NR2301Error as exc:
            last_error = exc
            print(
                "FACTORY_CONFIG_API_NOT_READY"
                f" attempt={attempt}"
                f" field={getattr(exc, '_nr2301_snapshot_field', 'unknown')}"
                f" error={type(exc).__name__}",
                flush=True,
            )
            try:
                router.login()
            except NR2301Error:
                pass
            if attempt < attempts:
                time.sleep(delay)

    raise AssertionError(
        "configuration APIs did not become jointly ready: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )


def _timed_semantics(value):
    raw_time = value.get("time")
    if not isinstance(raw_time, str) or ":" not in raw_time:
        raise AssertionError("invalid timed reboot time")
    hour, minute = raw_time.split(":", 1)
    return (
        int(value.get("enable")),
        int(hour),
        int(minute),
        int(value.get("repeat")),
    )


def _timed_reboot_with_recovery(router, *, attempts=60, delay=1.0):
    last_error = None
    for attempt in range(attempts):
        try:
            return router.maintenance.timed_reboot(timeout=5.0)
        except NR2301Error as exc:
            last_error = exc
            try:
                router.login()
            except NR2301Error:
                pass
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise AssertionError(
        "timed reboot state did not become readable after factory reset: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )


def test_factory_reset_then_restore_original_backup(router):
    original_password = os.environ["NR2301_PASSWORD"]
    factory_password = os.environ["NR2301_FACTORY_PASSWORD"]

    before_state = _snapshot_with_recovery(router)
    original_timed = before_state["timed_reboot"]

    backup = router.maintenance.download_config_backup(timeout=30.0)
    print(
        "FACTORY_BACKUP"
        f" size={len(backup)}"
        f" sha256={hashlib.sha256(backup).hexdigest()}",
        flush=True,
    )

    marker_candidates = [
        ("23:57", 85),
        ("22:46", 170),
    ]
    original_semantics = _timed_semantics(original_timed)
    marker_time, marker_repeat = marker_candidates[0]
    if original_semantics == (0, 23, 57, 85):
        marker_time, marker_repeat = marker_candidates[1]

    marker = router.maintenance.set_timed_reboot(
        False,
        marker_time,
        marker_repeat,
        timeout=10.0,
    )
    marker_semantics = _timed_semantics(marker)
    assert marker_semantics != original_semantics

    factory_result = None
    try:
        factory_result = router.maintenance.factory_reset(
            factory_password,
            action_timeout=5.0,
            recovery_attempts=150,
            recovery_delay=1.0,
            recovery_timeout=4.0,
            initial_delay=2.0,
        )

        print(
            "FACTORY_RESET"
            f" boot_before={factory_result.get('boot_time_before')}"
            f" boot_after={factory_result.get('boot_time_after')}"
            f" outage_observed={factory_result.get('outage_observed')}"
            f" action_error={factory_result.get('action_error')!r}"
            f" credential_changed={factory_password != original_password}",
            flush=True,
        )

        assert factory_result["boot_time_after"] < factory_result["boot_time_before"]
        assert router.password == factory_password

        reset_timed = _timed_reboot_with_recovery(router)
        reset_semantics = _timed_semantics(reset_timed)

        print(
            "FACTORY_MARKER"
            f" synthetic_before={marker_semantics}"
            f" after_factory_reset={reset_semantics}",
            flush=True,
        )

        assert reset_semantics != marker_semantics

    finally:
        # The backup was captured before the synthetic marker. Restoring it is
        # therefore the cleanup path whether the factory-reset assertions pass
        # or a later verification step fails.
        restore_result = router.maintenance.restore_config_backup(
            backup,
            action_timeout=30.0,
            recovery_attempts=180,
            recovery_delay=1.0,
            recovery_timeout=4.0,
            initial_delay=2.0,
            recovery_password=original_password,
        )

        print(
            "FACTORY_RESTORE"
            f" boot_before={restore_result.get('boot_time_before')}"
            f" boot_after={restore_result.get('boot_time_after')}"
            f" outage_observed={restore_result.get('outage_observed')}"
            f" action_error={restore_result.get('action_error')!r}"
            f" uploaded_bytes={restore_result.get('uploaded_bytes')}"
            f" chunks={restore_result.get('chunk_count')}",
            flush=True,
        )

    after_state = _snapshot_with_recovery(router)
    assert after_state == before_state
    assert router.password == original_password

    backup_after = router.maintenance.download_config_backup(timeout=30.0)
    assert backup_after

    print(
        "FACTORY_FINAL"
        f" restored_state_equal={after_state == before_state}"
        f" backup_after_size={len(backup_after)}"
        f" backup_after_sha256={hashlib.sha256(backup_after).hexdigest()}",
        flush=True,
    )
