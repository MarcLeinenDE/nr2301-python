# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
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
