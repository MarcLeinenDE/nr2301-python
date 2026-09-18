# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_INTEGRATION") != "1":
    pytest.skip(
        "physical-router integration tests require NR2301_INTEGRATION=1",
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
        timeout=10.0,
    ) as client:
        client.login()
        yield client


def test_sensitive_configuration_reads_preserve_raw_objects_without_logging(router):
    # These endpoints can contain VPN, DDNS, extender, ACS or XMPP credentials.
    # Exercise only transport/shape and never print or snapshot concrete values.
    assert isinstance(router.vpn.profiles(), dict)
    assert isinstance(router.mobile.wan_settings(), dict)
    assert isinstance(router.ddns.settings(), dict)
    assert isinstance(router.tr069.config(), dict)
    assert isinstance(router.tr069.xmpp_config(), dict)


def test_legacy_dhcp_multicall_read(router):
    # The older getter is verified through a one-member multicall.
    response = router.lan.legacy_dhcp_settings()
    assert isinstance(response, dict)
    assert isinstance(response.get("dhcp"), dict)


def test_operator_scan_read_action(router):
    # Operator scan is read-oriented but may take longer than normal status reads.
    response = router.mobile.search_networks(timeout=60.0)
    assert isinstance(response, dict)
    if "network_list" in response:
        assert isinstance(response["network_list"], list)
