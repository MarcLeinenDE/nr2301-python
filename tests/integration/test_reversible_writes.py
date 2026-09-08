# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "reversible physical-router write tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")

    base_url = os.environ.get("NR2301_URL", "http://zyxel.home")
    username = os.environ.get("NR2301_USERNAME", "admin")

    with NR2301Client(
        base_url,
        username=username,
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        yield client


def _network_settings(router: NR2301Client) -> dict[str, object]:
    response = router.mobile.network_settings()
    settings = response.get("network_settings")
    assert isinstance(settings, Mapping)
    return dict(settings)


def _wps_enabled(router: NR2301Client) -> bool:
    response = router.wifi.wps()
    wireless = response.get("wireless")
    assert isinstance(wireless, Mapping)
    value = wireless.get("wps_enable")
    assert value in {"0", "1"}
    return value == "1"


def _sleep_wait_minutes(router: NR2301Client) -> int:
    response = router.device.sleep_wait_time()
    value = response.get("result")
    assert isinstance(value, int) and not isinstance(value, bool)
    assert value in {0, 10, 20, 30, 40, 60}
    return value


def _ui_language_state(router: NR2301Client) -> tuple[str, tuple[str, ...]]:
    language_response = router.device.ui_language()
    current = language_response.get("language")
    assert isinstance(current, str) and current

    info = router.device.info()
    raw_list = info.get("lang_list")
    assert isinstance(raw_list, str)
    available = tuple(part.strip() for part in raw_list.split(",") if part.strip())
    assert available
    assert current in available
    return current, available


def _canonical_timed_reboot_time(value: object) -> str:
    assert isinstance(value, str)
    match = re.fullmatch(r"([0-9]{1,2}):([0-9]{1,2})", value)
    assert match is not None
    hour = int(match.group(1))
    minute = int(match.group(2))
    assert 0 <= hour <= 23
    assert 0 <= minute <= 59
    return f"{hour:02d}:{minute:02d}"


def _timed_reboot_settings(router: NR2301Client) -> dict[str, object]:
    response = router.maintenance.timed_reboot()
    enable = response.get("enable")
    repeat = response.get("repeat")

    assert enable in {0, 1}
    assert isinstance(repeat, int) and not isinstance(repeat, bool)
    assert 0 <= repeat <= 255
    return {
        "enable": enable,
        "time": _canonical_timed_reboot_time(response.get("time")),
        "repeat": repeat,
    }


def test_data_roaming_toggle_and_restore(router: NR2301Client):
    before = _network_settings(router)
    original = before.get("data_roaming")
    assert original in {"0", "1"}
    target = original != "1"

    try:
        changed = router.mobile.set_data_roaming(target)
        assert changed.get("data_roaming") == ("1" if target else "0")
    finally:
        router.mobile.set_data_roaming(original == "1")

    restored = _network_settings(router)
    assert restored.get("data_roaming") == original


def test_network_mode_change_and_restore_when_alternative_exists(router: NR2301Client):
    before = _network_settings(router)
    original = before.get("network_mode")
    assert isinstance(original, str) and original

    available_response = router.mobile.available_network_modes()
    modes = available_response.get("network_modes")
    assert isinstance(modes, list)
    alternatives = [mode for mode in modes if isinstance(mode, str) and mode != original]
    if not alternatives:
        pytest.skip("router currently reports no alternative network mode")

    target = alternatives[0]
    try:
        changed = router.mobile.set_network_mode(target)
        assert changed.get("network_mode") == target
    finally:
        router.mobile.set_network_mode(original)

    restored = _network_settings(router)
    assert restored.get("network_mode") == original


def test_wps_toggle_and_restore(router: NR2301Client):
    original = _wps_enabled(router)

    try:
        changed = router.wifi.set_wps_enabled(not original)
        wireless = changed.get("wireless")
        assert isinstance(wireless, Mapping)
        assert wireless.get("wps_enable") == ("0" if original else "1")
    finally:
        router.wifi.set_wps_enabled(original)

    assert _wps_enabled(router) is original


def test_wifi_guest_and_split_state_machine_restores_original(router: NR2301Client):
    original_guest = router.wifi.guest_enabled()
    original_separate = router.wifi.uses_separate_ssids()

    try:
        router.wifi.set_guest_enabled(not original_guest)
        assert router.wifi.guest_enabled() is (not original_guest)
        assert router.wifi.uses_separate_ssids() is original_separate

        router.wifi.set_separate_ssids(not original_separate)
        assert router.wifi.uses_separate_ssids() is (not original_separate)
        assert router.wifi.guest_enabled() is (not original_guest)
    finally:
        # Each helper preserves the other dimension, so restoring split/combined
        # first and Guest second returns all four verified mode states safely.
        router.wifi.set_separate_ssids(original_separate)
        router.wifi.set_guest_enabled(original_guest)

    assert router.wifi.uses_separate_ssids() is original_separate
    assert router.wifi.guest_enabled() is original_guest


def test_sleep_wait_time_change_and_restore(router: NR2301Client):
    original = _sleep_wait_minutes(router)
    alternatives = [value for value in (0, 10, 20, 30, 40, 60) if value != original]
    target = alternatives[0]

    try:
        changed = router.device.set_sleep_wait_time(target)
        assert changed.get("result") == target
        assert _sleep_wait_minutes(router) == target
    finally:
        router.device.set_sleep_wait_time(original)

    assert _sleep_wait_minutes(router) == original


def test_ui_language_change_and_restore(router: NR2301Client):
    original, available = _ui_language_state(router)
    alternatives = [code for code in available if code != original]
    if not alternatives:
        pytest.skip("router currently reports no alternative UI language")

    # Prefer German on the tested router because it is a known advertised code,
    # otherwise use the first runtime-advertised alternative.
    target = "de" if "de" in alternatives else alternatives[0]

    try:
        changed = router.device.set_ui_language(target)
        assert changed.get("language") == target
        current, current_available = _ui_language_state(router)
        assert current == target
        assert current_available == available
    finally:
        router.device.set_ui_language(original)

    restored, restored_available = _ui_language_state(router)
    assert restored == original
    assert restored_available == available


def test_timed_reboot_disabled_probe_and_restore(router: NR2301Client):
    original = _timed_reboot_settings(router)
    original_enable = original["enable"]
    original_time = original["time"]
    original_repeat = original["repeat"]

    assert isinstance(original_enable, int)
    assert isinstance(original_time, str)
    assert isinstance(original_repeat, int)

    target_time = "23:58" if original_time != "23:58" else "23:57"
    target_repeat = original_repeat ^ 0x01

    try:
        # The probe schedule is deliberately disabled, so this test can verify
        # write/read-back semantics without creating an active reboot trigger.
        changed = router.maintenance.set_timed_reboot(False, target_time, target_repeat)
        assert changed.get("enable") == 0
        assert _canonical_timed_reboot_time(changed.get("time")) == target_time
        assert changed.get("repeat") == target_repeat
        assert _timed_reboot_settings(router) == {
            "enable": 0,
            "time": target_time,
            "repeat": target_repeat,
        }
    finally:
        router.maintenance.set_timed_reboot(
            original_enable == 1,
            original_time,
            original_repeat,
        )

    assert _timed_reboot_settings(router) == original
