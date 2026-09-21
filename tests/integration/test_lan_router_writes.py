# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ipaddress
import os

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical LAN/router write tests require "
        "NR2301_DESTRUCTIVE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        yield client


def _dhcp_fingerprint(value):
    keys = (
        "disabled",
        "lan_ip",
        "lan_netmask",
        "start",
        "end",
        "leasetime",
        "mtu",
        "dnsmode",
        "dns1",
        "dns2",
        "ipv6dns1",
        "ipv6dns2",
    )
    return tuple((key, value.get(key)) for key in keys)


def _reservation_fingerprint(items):
    return sorted(
        (
            str(item["index"]),
            str(item["mac"]).lower(),
            str(item["ip"]),
        )
        for item in items
    )


def _synthetic_reservation(original, dhcp):
    used_indices = {int(item["index"]) for item in original}
    free = next((index for index in range(10) if index not in used_indices), None)

    lan_ip = ipaddress.IPv4Address(dhcp["lan_ip"])
    network = ipaddress.IPv4Network(
        f"{dhcp['lan_ip']}/{dhcp['lan_netmask']}",
        strict=False,
    )
    pool_start = ipaddress.IPv4Address(dhcp["start"])
    pool_end = ipaddress.IPv4Address(dhcp["end"])
    used_ips = {
        ipaddress.IPv4Address(item["ip"])
        for item in original
    }

    candidate_ip = None
    lower = int(network.network_address) + 1
    upper = int(network.broadcast_address) - 1
    for raw in range(upper, lower - 1, -1):
        candidate = ipaddress.IPv4Address(raw)
        if candidate == lan_ip:
            continue
        if candidate in used_ips:
            continue
        if pool_start <= candidate <= pool_end:
            continue
        candidate_ip = str(candidate)
        break

    if candidate_ip is None:
        raise AssertionError(
            "no free static-reservation address exists inside the LAN subnet "
            "and outside the DHCP pool"
        )

    used_macs = {str(item["mac"]).lower() for item in original}
    mac = next(
        (
            candidate
            for candidate in (
                "02:00:00:00:00:fe",
                "02:00:00:00:00:fd",
                "02:00:00:00:00:fc",
            )
            if candidate not in used_macs
        ),
        None,
    )
    if mac is None:
        raise AssertionError("could not construct a distinct synthetic MAC")

    if free is not None:
        candidate = {"index": free, "mac": mac, "ip": candidate_ip}
        return [dict(item) for item in original] + [candidate]

    # All slots occupied: temporarily replace the highest slot. The complete
    # original table is restored in finally.
    target = max(original, key=lambda item: int(item["index"]))
    candidate = {
        "index": int(target["index"]),
        "mac": mac,
        "ip": candidate_ip,
    }
    return [
        candidate if int(item["index"]) == int(target["index"]) else dict(item)
        for item in original
    ]


def test_lan_router_write_lifecycle_and_exact_restore(router):
    original_dhcp = router.lan.dhcp(timeout=5.0)
    original_reservations = router.lan.static_reservation_list(timeout=5.0)
    original_address = router.lan.address(timeout=5.0)
    original_mode = router.device.work_mode(timeout=5.0)

    original_dhcp_fp = _dhcp_fingerprint(original_dhcp)
    original_reservation_fp = _reservation_fingerprint(original_reservations)

    router_address = original_address.get("router")
    if not isinstance(router_address, dict):
        pytest.fail("router_get_lan_ip returned no router object")
    lan_ip = router_address.get("lan_ip")
    lan_netmask = router_address.get("lan_netmask")
    if not isinstance(lan_ip, str) or not isinstance(lan_netmask, str):
        pytest.fail("router_get_lan_ip returned invalid address fields")

    mode = original_mode.get("work_mode")
    if mode not in {"router", "bridge"}:
        pytest.fail("router_get_work_mode returned an unknown mode")

    mutated_dhcp = dict(original_dhcp)
    mutated_dhcp["leasetime"] = (
        "43200" if original_dhcp.get("leasetime") != "43200" else "86400"
    )
    synthetic_reservations = _synthetic_reservation(
        [dict(item) for item in original_reservations],
        original_dhcp,
    )

    dhcp_attempted = False
    reservations_attempted = False

    try:
        dhcp_attempted = True
        verified_dhcp = router.lan.set_dhcp_settings(
            mutated_dhcp,
            recovery_attempts=30,
            recovery_delay=1.0,
            recovery_timeout=4.0,
        )
        assert _dhcp_fingerprint(verified_dhcp) == _dhcp_fingerprint(mutated_dhcp)
        assert _dhcp_fingerprint(verified_dhcp) != original_dhcp_fp
        print(
            "LAN_DHCP_WRITE"
            " field=leasetime"
            " changed=True"
            " readback=True",
            flush=True,
        )

        reservations_attempted = True
        verified_reservations = router.lan.set_static_reservations(
            synthetic_reservations,
            recovery_attempts=30,
            recovery_delay=1.0,
            recovery_timeout=4.0,
        )
        assert _reservation_fingerprint(verified_reservations) == (
            _reservation_fingerprint(synthetic_reservations)
        )
        assert _reservation_fingerprint(verified_reservations) != (
            original_reservation_fp
        )
        print(
            "LAN_STATIC_RESERVATION_WRITE"
            f" original_count={len(original_reservations)}"
            f" synthetic_count={len(synthetic_reservations)}"
            " readback=True",
            flush=True,
        )

        verified_address = router.lan.set_address_legacy(
            lan_ip,
            lan_netmask,
            force=True,
            recovery_attempts=30,
            recovery_delay=1.0,
            recovery_timeout=4.0,
        )
        verified_router = verified_address.get("router")
        assert isinstance(verified_router, dict)
        assert verified_router.get("lan_ip") == lan_ip
        assert verified_router.get("lan_netmask") == lan_netmask
        print(
            "LAN_LEGACY_ADDRESS_WRITE force_same_state=True readback=True",
            flush=True,
        )

        verified_mode = router.device.set_work_mode(
            mode,
            force=True,
            recovery_attempts=30,
            recovery_delay=1.0,
            recovery_timeout=4.0,
        )
        assert verified_mode.get("work_mode") == mode
        print(
            "ROUTER_WORK_MODE_WRITE"
            f" force_same_state=True"
            f" mode_preserved=True",
            flush=True,
        )

    finally:
        if reservations_attempted:
            restored_reservations = router.lan.set_static_reservations(
                [dict(item) for item in original_reservations],
                recovery_attempts=30,
                recovery_delay=1.0,
                recovery_timeout=4.0,
            )
            assert _reservation_fingerprint(restored_reservations) == (
                original_reservation_fp
            )

        if dhcp_attempted:
            restored_dhcp = router.lan.set_dhcp_settings(
                dict(original_dhcp),
                recovery_attempts=30,
                recovery_delay=1.0,
                recovery_timeout=4.0,
            )
            assert _dhcp_fingerprint(restored_dhcp) == original_dhcp_fp

    final_dhcp = router.lan.dhcp(timeout=5.0)
    final_reservations = router.lan.static_reservation_list(timeout=5.0)
    final_address = router.lan.address(timeout=5.0)
    final_mode = router.device.work_mode(timeout=5.0)

    assert _dhcp_fingerprint(final_dhcp) == original_dhcp_fp
    assert _reservation_fingerprint(final_reservations) == original_reservation_fp
    assert final_address == original_address
    assert final_mode == original_mode

    print(
        "LAN_ROUTER_FINAL"
        " dhcp_restored=True"
        " reservations_restored=True"
        " address_preserved=True"
        " work_mode_preserved=True",
        flush=True,
    )
