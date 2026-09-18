# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical VPN write tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration

_NAME_A = "SDK-VPN-PROD"
_NAME_B = "SDK-VPN-PROD-EDIT"


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


def _profiles(response):
    value = response.get("vpn_clients")
    if not isinstance(value, list):
        pytest.fail("get_vpn_clients did not return a profile list")
    return value


def _profile_index(profile):
    value = profile.get("index")
    if isinstance(value, bool):
        pytest.fail("VPN profile returned invalid index")
    if isinstance(value, int):
        if value < 0:
            pytest.fail("VPN profile returned negative index")
        return str(value)
    if isinstance(value, str) and value.strip().isdigit():
        return str(int(value.strip()))
    pytest.fail("VPN profile returned unusable index")


def _active_index(response):
    value = response.get("vpn_client_active_index")
    if value in {None, "", "-1", -1, "disable"}:
        return None
    if isinstance(value, bool):
        pytest.fail("get_vpn_clients returned invalid active index")
    if isinstance(value, int):
        if value < 0:
            pytest.fail("get_vpn_clients returned invalid active index")
        return str(value)
    if isinstance(value, str) and value.strip().isdigit():
        return str(int(value.strip()))
    pytest.fail("get_vpn_clients returned unknown active-index sentinel")


def _public_profile_state(response):
    result = {}
    for item in _profiles(response):
        if not isinstance(item, Mapping):
            pytest.fail("get_vpn_clients returned a non-object profile")
        index = _profile_index(item)
        result[index] = (
            item.get("vpn_name"),
            item.get("protocol_type"),
            item.get("vpn_server"),
            item.get("vpn_user_name"),
        )
    return result


def _cleanup_synthetic(router):
    state = router.vpn.profiles()
    for item in list(_profiles(state)):
        if not isinstance(item, Mapping):
            continue
        if item.get("vpn_name") not in {_NAME_A, _NAME_B}:
            continue
        index = _profile_index(item)
        # Direct normalized endpoint fallback: cleanup must not depend on the
        # high-level helper that is currently under physical test.
        router.call("cm", "del_vpn_client_item", data={"index": index})


def _restore_active_state(router, original_active):
    state = router.vpn.profiles()
    current_active = _active_index(state)

    if original_active is not None:
        existing = {_profile_index(item) for item in _profiles(state) if isinstance(item, Mapping)}
        if original_active not in existing:
            pytest.fail("original active VPN profile disappeared during test")
        if current_active != original_active:
            # Active-profile selection is meaningful with the subsystem enabled.
            router.vpn.set_enabled(True)
            router.vpn.set_profile_active(original_active, True)
        return

    if current_active is not None:
        router.vpn.set_enabled(True)
        router.vpn.set_profile_active(current_active, False)


def test_vpn_profile_write_lifecycle_and_restore(router):
    initial = router.vpn.profiles()
    original_profiles = _public_profile_state(initial)
    original_enable = initial.get("vpn_client_enable")
    original_active = _active_index(initial)

    if original_enable not in {"enable", "disable"}:
        pytest.fail("get_vpn_clients returned invalid global enable state")

    # A pre-existing profile with our reserved synthetic name would make
    # deterministic cleanup ambiguous. Abort before any mutation in that one
    # case; ordinary existing real profiles are fully supported by this test.
    for item in _profiles(initial):
        if isinstance(item, Mapping) and item.get("vpn_name") in {_NAME_A, _NAME_B}:
            pytest.fail("reserved synthetic VPN profile name already exists")

    runtime_before = router.device.runtime().get("boot_time")

    try:
        added = router.vpn.add_profile(
            name=_NAME_A,
            protocol="pptp",
            server="vpn.example.invalid",
            username="sdk-user",
            password="sdk-password",
        )
        synthetic_index = _profile_index(added)

        edited = router.vpn.edit_profile(
            synthetic_index,
            name=_NAME_B,
            protocol="l2tp/ipsec",
            server="vpn-edited.example.invalid",
            username="sdk-user-edit",
            password="sdk-password-edit",
            secure="sdk-psk",
        )
        assert edited.get("vpn_name") == _NAME_B
        assert edited.get("protocol_type") == "l2tp/ipsec"

        # Exercise profile selection against a real enabled subsystem. The
        # synthetic server is deliberately non-routable by DNS convention.
        enabled = router.vpn.set_enabled(True)
        assert enabled.get("vpn_client_enable") == "enable"

        active = router.vpn.set_profile_active(synthetic_index, True)
        assert _active_index(active) == synthetic_index

        inactive = router.vpn.set_profile_active(synthetic_index, False)
        assert _active_index(inactive) != synthetic_index

        deleted = router.vpn.delete_profile(synthetic_index)
        assert synthetic_index not in _public_profile_state(deleted)

        # Exercise both global transitions, independent of the initial state.
        disabled = router.vpn.set_enabled(False)
        assert disabled.get("vpn_client_enable") == "disable"
        reenabled = router.vpn.set_enabled(True)
        assert reenabled.get("vpn_client_enable") == "enable"

    finally:
        _cleanup_synthetic(router)
        _restore_active_state(router, original_active)

        restored = router.vpn.set_enabled(original_enable == "enable")
        if restored.get("vpn_client_enable") != original_enable:
            pytest.fail("VPN global enable state was not restored")

        final = router.vpn.profiles()
        if _public_profile_state(final) != original_profiles:
            pytest.fail("pre-existing VPN profile state was not restored")
        if _active_index(final) != original_active:
            pytest.fail("VPN active-profile selection was not restored")

    runtime_after = router.device.runtime().get("boot_time")
    if isinstance(runtime_before, int) and isinstance(runtime_after, int):
        assert runtime_after >= runtime_before
