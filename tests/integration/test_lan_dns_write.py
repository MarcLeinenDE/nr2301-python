# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "reversible physical-router write tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration

_DNS_FIELDS = {"dnsmode", "dns1", "dns2", "ipv6dns1", "ipv6dns2"}
_REQUIRED_COMBINED_FIELDS = {
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
}


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


def _restore_dns(router: NR2301Client, before: dict[str, object]) -> None:
    mode = before.get("dnsmode")
    if mode == "auto":
        router.lan.set_dns_auto(
            write_timeout=30,
            recovery_attempts=20,
            recovery_delay=1.0,
            recovery_timeout=3.0,
        )
        return

    if mode != "manual":
        raise AssertionError(f"unsupported original DNS mode for restore: {mode!r}")

    router.lan.set_dns(
        str(before.get("dns1", "")),
        str(before.get("dns2", "")),
        ipv6_primary=str(before.get("ipv6dns1", "")),
        ipv6_secondary=str(before.get("ipv6dns2", "")),
        write_timeout=30,
        recovery_attempts=20,
        recovery_delay=1.0,
        recovery_timeout=3.0,
    )


def test_combined_dhcp_dns_write_preserves_non_dns_fields_and_restores(router: NR2301Client):
    before = dict(router.lan.dhcp())
    assert _REQUIRED_COMBINED_FIELDS.issubset(before)
    assert before.get("dnsmode") in {"auto", "manual"}

    # Use a real, syntactically valid resolver pair for the short-lived test so
    # the router does not lose DNS merely because the values are documentation
    # placeholders. Pick the pair that is not already the current manual pair.
    current_pair = (before.get("dns1"), before.get("dns2"))
    candidates = [
        ("1.1.1.1", "1.0.0.1"),
        ("8.8.8.8", "8.8.4.4"),
    ]
    target_primary, target_secondary = next(
        pair for pair in candidates if pair != current_pair
    )

    try:
        changed_dns = router.lan.set_dns(
            target_primary,
            target_secondary,
            write_timeout=30,
            recovery_attempts=20,
            recovery_delay=1.0,
            recovery_timeout=3.0,
        )
        assert changed_dns == {
            "dnsmode": "manual",
            "dns1": target_primary,
            "dns2": target_secondary,
            "ipv6dns1": "",
            "ipv6dns2": "",
        }

        changed_full = dict(router.lan.dhcp())
        assert _REQUIRED_COMBINED_FIELDS.issubset(changed_full)

        # The router setter is a combined 12-field object. The SDK must preserve
        # every non-DNS field exactly while modifying only the five DNS fields.
        for key in _REQUIRED_COMBINED_FIELDS - _DNS_FIELDS:
            assert changed_full.get(key) == before.get(key), (
                f"combined DHCP setter changed unrelated field {key!r}: "
                f"before={before.get(key)!r}, after={changed_full.get(key)!r}"
            )
    finally:
        _restore_dns(router, before)

    restored = dict(router.lan.dhcp())
    assert restored == before
