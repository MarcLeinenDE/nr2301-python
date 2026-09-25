# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ipaddress
import os
import time
from collections.abc import Mapping
from typing import Any

import pytest

from nr2301 import NR2301Client, NR2301Error


if os.environ.get("NR2301_DESTRUCTIVE_INTEGRATION") != "1":
    pytest.skip(
        "physical DMZ-destination recovery test requires "
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


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        pytest.fail(f"{label} did not return an object")
    return value


def _firewall(response: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    return _mapping(response.get("firewall"), f"{label}.firewall")


def _binary(value: Any, label: str) -> int:
    if isinstance(value, bool):
        pytest.fail(f"{label} returned boolean instead of 0/1")
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        pytest.fail(f"{label} did not return 0/1")
    if numeric not in {0, 1}:
        pytest.fail(f"{label} returned unsupported value {numeric!r}")
    return numeric


def _snapshot(router, *, timeout: float = 10.0) -> dict[str, object]:
    dmz_info = _firewall(router.firewall.dmz_info(timeout=timeout), "dmz_info")
    dmz_disable = _firewall(
        router.firewall.disable_info(timeout=timeout), "dmz_disable"
    ).get("dmz_disable")
    admin = _firewall(
        router.firewall.admin_from_wan(timeout=timeout), "admin_from_wan"
    ).get("admin_from_wan_enable")
    ping = _firewall(
        router.firewall.ping_from_wan(timeout=timeout), "ping_from_wan"
    ).get("ping_from_wan_enable")
    upnp = _firewall(router.firewall.upnp_state(timeout=timeout), "upnp").get(
        "upnp_enable"
    )
    vpn = router.firewall.vpn_passthrough(timeout=timeout)

    destination = dmz_info.get("dmz_dest_ip")
    if not isinstance(destination, str):
        pytest.fail("dmz_info did not return string dmz_dest_ip")

    return {
        "dmz_destination": destination,
        "dmz_enabled": 1 - _binary(dmz_disable, "dmz_disable"),
        "admin_from_wan": _binary(admin, "admin_from_wan"),
        "ping_from_wan": _binary(ping, "ping_from_wan"),
        "upnp_enabled": _binary(upnp, "upnp"),
        "vpn": (
            _binary(vpn.get("pptp"), "vpn.pptp"),
            _binary(vpn.get("l2tp"), "vpn.l2tp"),
            _binary(vpn.get("ipsec"), "vpn.ipsec"),
        ),
    }


def _snapshot_with_recovery(
    router,
    *,
    attempts: int = 12,
    timeout: float = 10.0,
) -> dict[str, object]:
    last_error: NR2301Error | None = None
    for attempt in range(attempts):
        try:
            return _snapshot(router, timeout=timeout)
        except NR2301Error as exc:
            last_error = exc
            try:
                router.login()
            except NR2301Error:
                pass
            if attempt + 1 < attempts:
                time.sleep(1.0)
    raise AssertionError(
        "Firewall state did not become readable after config restore: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )


def _is_valid_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError:
        return False
    return True


def _synthetic_destination(router, original: str) -> str:
    response = router.lan.address(timeout=5.0)
    values = _mapping(response.get("router"), "router_get_lan_ip.router")
    lan_ip = values.get("lan_ip")
    netmask = values.get("lan_netmask")
    if not isinstance(lan_ip, str) or not isinstance(netmask, str):
        pytest.fail("router_get_lan_ip did not return LAN IPv4/netmask strings")

    try:
        address = ipaddress.IPv4Address(lan_ip)
        network = ipaddress.IPv4Network(f"{lan_ip}/{netmask}", strict=False)
    except ValueError as exc:
        pytest.fail(f"router_get_lan_ip returned invalid IPv4 settings: {exc}")

    # Prefer high usable addresses without enumerating the whole subnet.
    for offset in range(1, 32):
        candidate_int = int(network.broadcast_address) - offset
        if candidate_int <= int(network.network_address):
            break
        candidate = ipaddress.IPv4Address(candidate_int)
        text = str(candidate)
        if candidate != address and text != original:
            return text

    # The API contract has already physically accepted a documentation-only
    # IPv4 value. This fallback is only for an unusually tiny LAN prefix.
    if original != "192.0.2.10":
        return "192.0.2.10"
    return "192.0.2.11"


def test_dmz_destination_write_and_recovery(router):
    original = _snapshot_with_recovery(router)
    original_destination = str(original["dmz_destination"])
    synthetic = _synthetic_destination(router, original_destination)

    # Keep a secret-bearing backup only in memory. It is never printed,
    # persisted by the test, or committed.
    backup = router.maintenance.download_config_backup(timeout=30.0)
    assert backup

    original_setter_restorable = _is_valid_ipv4(original_destination)
    restore_via_backup = not original_setter_restorable
    backup_used = False

    print(
        "FIREWALL_DMZ_DESTINATION_PREP"
        f" original_setter_restorable={original_setter_restorable}"
        f" backup_restore_required={restore_via_backup}"
        " backup_ready=True",
        flush=True,
    )

    try:
        if not bool(original["dmz_enabled"]):
            router.firewall.set_dmz_enabled(True, timeout=10.0)

        router.firewall.set_dmz_destination(synthetic, timeout=10.0)
        current = _snapshot(router)
        assert current["dmz_destination"] == synthetic

        print(
            "FIREWALL_DMZ_DESTINATION_WRITE changed=True readback=True",
            flush=True,
        )

    finally:
        if restore_via_backup:
            result = router.maintenance.restore_config_backup(
                backup,
                action_timeout=30.0,
                recovery_attempts=150,
                recovery_delay=1.0,
                recovery_timeout=4.0,
                initial_delay=2.0,
            )
            backup_used = True
            print(
                "FIREWALL_DMZ_DESTINATION_RESTORE"
                " method=config_backup"
                f" outage_observed={result.get('outage_observed')}"
                f" reboot_evidence={result.get('reboot_evidence')}",
                flush=True,
            )
        else:
            setter_restore_ok = False
            try:
                router.firewall.set_dmz_destination(
                    original_destination, timeout=10.0
                )
                router.firewall.set_dmz_enabled(
                    bool(original["dmz_enabled"]), timeout=10.0
                )
                restored = _snapshot_with_recovery(router)
                setter_restore_ok = (
                    restored["dmz_destination"] == original_destination
                    and restored["dmz_enabled"] == original["dmz_enabled"]
                )
            except NR2301Error:
                setter_restore_ok = False

            if setter_restore_ok:
                print(
                    "FIREWALL_DMZ_DESTINATION_RESTORE method=setter readback=True",
                    flush=True,
                )
            else:
                result = router.maintenance.restore_config_backup(
                    backup,
                    action_timeout=30.0,
                    recovery_attempts=150,
                    recovery_delay=1.0,
                    recovery_timeout=4.0,
                    initial_delay=2.0,
                )
                backup_used = True
                print(
                    "FIREWALL_DMZ_DESTINATION_RESTORE"
                    " method=config_backup_fallback"
                    f" outage_observed={result.get('outage_observed')}"
                    f" reboot_evidence={result.get('reboot_evidence')}",
                    flush=True,
                )

    final = _snapshot_with_recovery(router)
    assert final == original
    print(
        "FIREWALL_DMZ_DESTINATION_FINAL restored=True"
        f" backup_used={backup_used}",
        flush=True,
    )
