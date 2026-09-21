# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import os
import time

import pytest

from nr2301 import NR2301Client, NR2301Error


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical configuration restore tests require "
        "NR2301_DESTRUCTIVE_INTEGRATION=1",
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
        timeout=15.0,
    ) as client:
        client.login()
        yield client


def _stable_config_snapshot(router):
    """Read only stable configuration state; exclude dynamic runtime/radio data."""

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

    snapshot = {}
    for name, reader in readers.items():
        try:
            snapshot[name] = reader()
        except NR2301Error as exc:
            setattr(exc, "_nr2301_snapshot_field", name)
            raise
    return snapshot


def _stable_config_snapshot_with_recovery(
    router,
    *,
    attempts=60,
    delay=1.0,
):
    """Wait until all compared configuration namespaces are API-ready."""

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            snapshot = _stable_config_snapshot(router)
            if attempt > 1:
                print(
                    "CONFIG_API_READY"
                    f" attempt={attempt}"
                    f" previous_error={type(last_error).__name__ if last_error else None}",
                    flush=True,
                )
            return snapshot
        except NR2301Error as exc:
            last_error = exc
            print(
                "CONFIG_API_NOT_READY"
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
        "configuration APIs did not become jointly ready after restore: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_download_restore_same_backup_and_verify_configuration(router):
    before_state = _stable_config_snapshot_with_recovery(router)

    backup = router.maintenance.download_config_backup(timeout=30.0)
    before_hash = _sha256(backup)

    print(
        "CONFIG_BACKUP"
        f" size={len(backup)}"
        f" sha256={before_hash}",
        flush=True,
    )

    result = router.maintenance.restore_config_backup(
        backup,
        action_timeout=30.0,
        recovery_attempts=150,
        recovery_delay=1.0,
        recovery_timeout=4.0,
        initial_delay=2.0,
    )

    print(
        "CONFIG_RESTORE"
        f" boot_before={result.get('boot_time_before')}"
        f" boot_after={result.get('boot_time_after')}"
        f" outage_observed={result.get('outage_observed')}"
        f" action_error={result.get('action_error')!r}"
        f" uploaded_bytes={result.get('uploaded_bytes')}"
        f" chunks={result.get('chunk_count')}",
        flush=True,
    )

    assert result["boot_time_after"] < result["boot_time_before"]
    assert result["uploaded_bytes"] == len(backup)
    assert result["chunk_count"] >= 1

    after_state = _stable_config_snapshot_with_recovery(
        router,
        attempts=90,
        delay=1.0,
    )
    assert after_state == before_state

    # Reconfirm that the stock backup download endpoint remains usable after
    # restore/reboot. The backup file itself is never printed or persisted.
    backup_after = router.maintenance.download_config_backup(timeout=30.0)
    after_hash = _sha256(backup_after)

    print(
        "CONFIG_BACKUP_AFTER_RESTORE"
        f" size={len(backup_after)}"
        f" sha256={after_hash}",
        flush=True,
    )

    assert backup_after
