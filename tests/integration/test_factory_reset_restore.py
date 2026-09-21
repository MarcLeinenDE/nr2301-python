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
    temporary_password = os.environ.get("NR2301_FACTORY_TEST_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required")
    if not factory_password:
        pytest.skip(
            "NR2301_FACTORY_PASSWORD is required; use the device-specific "
            "default admin password shown on the NR2301 LCD"
        )
    if not temporary_password:
        pytest.skip(
            "NR2301_FACTORY_TEST_PASSWORD is required for credential "
            "reset/restore verification"
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
    temporary_password = os.environ["NR2301_FACTORY_TEST_PASSWORD"]

    if temporary_password in {original_password, factory_password}:
        pytest.fail(
            "NR2301_FACTORY_TEST_PASSWORD must differ from the original/default password"
        )

    before_state = _snapshot_with_recovery(router)
    original_timed = before_state["timed_reboot"]

    # Baseline backup is captured before any credential mutation. This is the
    # final cleanup artifact and returns the router to the exact starting
    # credential/configuration state.
    baseline_backup = router.maintenance.download_config_backup(timeout=30.0)
    print(
        "FACTORY_BASELINE_BACKUP"
        f" size={len(baseline_backup)}"
        f" sha256={hashlib.sha256(baseline_backup).hexdigest()}",
        flush=True,
    )

    main_result = None
    try:
        password_result = router.account.set_password(
            temporary_password,
            timeout=10.0,
            verify_login=True,
        )
        assert int(password_result.get("result")) == 0
        assert router.password == temporary_password

        # This backup deliberately contains the temporary password. Restoring
        # it after factory reset must therefore change the credential away from
        # the factory/default value again.
        test_backup = router.maintenance.download_config_backup(timeout=30.0)
        print(
            "FACTORY_TEST_BACKUP"
            f" size={len(test_backup)}"
            f" sha256={hashlib.sha256(test_backup).hexdigest()}",
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
            f" credential_reset={router.password == factory_password}",
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

        # Restore the backup that contains the temporary password. Recovery
        # must therefore use that temporary credential.
        test_restore = router.maintenance.restore_config_backup(
            test_backup,
            action_timeout=30.0,
            recovery_attempts=180,
            recovery_delay=1.0,
            recovery_timeout=4.0,
            initial_delay=2.0,
            recovery_password=temporary_password,
        )

        print(
            "FACTORY_TEST_RESTORE"
            f" boot_before={test_restore.get('boot_time_before')}"
            f" boot_after={test_restore.get('boot_time_after')}"
            f" outage_observed={test_restore.get('outage_observed')}"
            f" action_error={test_restore.get('action_error')!r}"
            f" uploaded_bytes={test_restore.get('uploaded_bytes')}"
            f" chunks={test_restore.get('chunk_count')}"
            f" credential_restored={router.password == temporary_password}"
            f" reboot_evidence={test_restore.get('reboot_evidence')!r}",
            flush=True,
        )

        assert test_restore["reboot_evidence"] in {
            "boot_time_reset",
            "outage_plus_fresh_uptime",
        }
        assert test_restore["credential_recovery_verified"] is True
        assert router.password == temporary_password

        restored_test_state = _snapshot_with_recovery(router)
        assert restored_test_state == before_state

        # A fresh account read proves that the new credential-backed session
        # is usable after the restore; the raw response is intentionally not
        # printed because it can contain sensitive account fields.
        account_info = router.account.info(timeout=5.0)
        assert int(account_info.get("result")) == 0

        main_result = {
            "factory_reset": factory_result,
            "test_restore": test_restore,
        }

    finally:
        # Always restore the original pre-mutation backup. It contains the
        # device-default/original administrator password and all original
        # settings. recovery_password switches the client back to that
        # credential after the final reboot.
        baseline_restore = router.maintenance.restore_config_backup(
            baseline_backup,
            action_timeout=30.0,
            recovery_attempts=180,
            recovery_delay=1.0,
            recovery_timeout=4.0,
            initial_delay=2.0,
            recovery_password=original_password,
        )

        print(
            "FACTORY_BASELINE_RESTORE"
            f" boot_before={baseline_restore.get('boot_time_before')}"
            f" boot_after={baseline_restore.get('boot_time_after')}"
            f" outage_observed={baseline_restore.get('outage_observed')}"
            f" action_error={baseline_restore.get('action_error')!r}"
            f" uploaded_bytes={baseline_restore.get('uploaded_bytes')}"
            f" chunks={baseline_restore.get('chunk_count')}"
            f" original_credential_restored={router.password == original_password}"
            f" reboot_evidence={baseline_restore.get('reboot_evidence')!r}",
            flush=True,
        )

        assert baseline_restore["reboot_evidence"] in {
            "boot_time_reset",
            "outage_plus_fresh_uptime",
        }
        assert baseline_restore["credential_recovery_verified"] is True

        final_state = _snapshot_with_recovery(router)
        assert final_state == before_state
        assert router.password == original_password

        backup_after = router.maintenance.download_config_backup(timeout=30.0)
        assert backup_after

        print(
            "FACTORY_FINAL"
            f" restored_state_equal={final_state == before_state}"
            f" backup_after_size={len(backup_after)}"
            f" backup_after_sha256={hashlib.sha256(backup_after).hexdigest()}",
            flush=True,
        )

    assert main_result is not None
