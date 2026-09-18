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
        pytest.fail("synthetic VPN profile returned invalid index")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip().isdigit():
        return str(int(value.strip()))
    pytest.fail("synthetic VPN profile returned unusable index")


def _cleanup_synthetic(router):
    state = router.vpn.profiles()
    for item in list(_profiles(state)):
        if not isinstance(item, Mapping):
            continue
        if item.get("vpn_name") not in {_NAME_A, _NAME_B}:
            continue
        index = _profile_index(item)
        # Use the already-normalized exact endpoint as a cleanup fallback so a
        # failure in the high-level delete helper cannot strand test residue.
        router.call("cm", "del_vpn_client_item", data={"index": index})


def test_vpn_profile_write_lifecycle_and_restore(router):
    initial = router.vpn.profiles()
    existing = _profiles(initial)
    if existing:
        pytest.skip(
            "physical VPN write smoke requires an empty profile list to avoid "
            "touching existing secret-bearing profiles"
        )

    original_enable = initial.get("vpn_client_enable")
    if original_enable not in {"enable", "disable"}:
        pytest.fail("get_vpn_clients returned invalid global enable state")

    runtime_before = router.device.runtime().get("boot_time")
    synthetic_index = None

    try:
        # Keep the subsystem disabled while the synthetic profile exists. This
        # prevents the fake server from becoming an intentional tunnel target.
        router.vpn.set_enabled(False)

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

        active = router.vpn.set_profile_active(synthetic_index, True)
        assert str(active.get("vpn_client_active_index")) == synthetic_index

        inactive = router.vpn.set_profile_active(synthetic_index, False)
        assert str(inactive.get("vpn_client_active_index")) != synthetic_index

        deleted = router.vpn.delete_profile(synthetic_index)
        assert _profiles(deleted) == []
        synthetic_index = None

        # Exercise a real global-state transition only after the synthetic
        # profile has been removed. With an empty list this cannot start a VPN
        # tunnel.
        if original_enable == "disable":
            assert router.vpn.set_enabled(True).get("vpn_client_enable") == "enable"
            assert router.vpn.set_enabled(False).get("vpn_client_enable") == "disable"
        else:
            assert router.vpn.set_enabled(True).get("vpn_client_enable") == "enable"

    finally:
        _cleanup_synthetic(router)

        final = router.vpn.profiles()
        if _profiles(final):
            pytest.fail("synthetic VPN profile residue remains after cleanup")

        expected_enabled = original_enable == "enable"
        restored = router.vpn.set_enabled(expected_enabled)
        if restored.get("vpn_client_enable") != original_enable:
            pytest.fail("VPN global enable state was not restored")

    runtime_after = router.device.runtime().get("boot_time")
    if isinstance(runtime_before, int) and isinstance(runtime_after, int):
        assert runtime_after >= runtime_before
