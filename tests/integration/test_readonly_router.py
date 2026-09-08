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

    # The tested firmware resolves zyxel.home to 192.168.1.1 but treats
    # administrator pre-auth calls differently by HTTP host/authority. The
    # canonical hostname succeeds; the direct IP returns result=4.
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


def _assert_mapping(value):
    assert isinstance(value, dict)


def test_version_read(router):
    _assert_mapping(router.version.info())


def test_device_health_reads(router):
    # Deliberately avoid device.info() / mac_info() here: those responses can
    # contain IMEI/IMSI/ICCID/serial/MAC identifiers that are unnecessary for
    # a routine smoke test.
    _assert_mapping(router.device.runtime())
    _assert_mapping(router.device.diagnostics())
    _assert_mapping(router.device.internet())
    _assert_mapping(router.device.features())
    _assert_mapping(router.device.work_mode())
    _assert_mapping(router.device.battery())
    _assert_mapping(router.device.sleep_wait_time())


def test_sim_status_read(router):
    status = router.sim.status()
    _assert_mapping(status)
    assert isinstance(status.get("pin_puk"), dict)


def test_mobile_status_reads(router):
    _assert_mapping(router.mobile.cell_info())
    _assert_mapping(router.mobile.wan_info())
    _assert_mapping(router.mobile.available_network_modes())
    _assert_mapping(router.mobile.network_select_mode())
    _assert_mapping(router.mobile.network_settings())


def test_lan_dns_reads(router):
    _assert_mapping(router.lan.address())
    _assert_mapping(router.lan.dns())


def test_firewall_reads(router):
    # Firewall/NAT reads can contain private addresses, URL-filter entries or
    # forwarding rules. Exercise the live-verified read contracts without
    # printing or asserting the concrete configuration values.
    _assert_mapping(router.firewall.disable_info())
    _assert_mapping(router.firewall.dmz_info())
    _assert_mapping(router.firewall.vpn_passthrough())
    _assert_mapping(router.firewall.admin_from_wan())
    _assert_mapping(router.firewall.ping_from_wan())
    _assert_mapping(router.firewall.port_forward())
    _assert_mapping(router.firewall.port_trigger())
    _assert_mapping(router.firewall.url_filter())
    _assert_mapping(router.firewall.ip_filter_mode_state())
    _assert_mapping(router.firewall.port_filter_mode_state())
    _assert_mapping(router.firewall.upnp_state())


def test_ota_reads(router):
    # Read current OTA state only. Do not call manual_check_update,
    # download_update, abandon/clear actions or any install path.
    updated_status = router.ota.updated_status()
    query_state = router.ota.query_state()

    _assert_mapping(updated_status)
    _assert_mapping(query_state)
    assert isinstance(updated_status.get("fota_auto_upgrade_status"), str)
    assert isinstance(updated_status.get("result"), str)
    assert isinstance(query_state.get("response"), str)


def test_wifi_status_reads(router):
    # Avoid wifi.config(): it includes SSIDs and Wi-Fi keys. The smoke suite
    # needs only non-secret status surfaces.
    _assert_mapping(router.wifi.basic_info())
    _assert_mapping(router.wifi.wps())
    _assert_mapping(router.wifi.wps_status())
    _assert_mapping(router.wifi.extender_status())


def test_sms_summary_read(router):
    # Summary only: do not list mailbox nodes/message bodies in this smoke test.
    _assert_mapping(router.sms.brief_info())


def test_statistics_reads(router):
    _assert_mapping(router.statistics.traffic())
    _assert_mapping(router.statistics.traffic_transport_status())
    _assert_mapping(router.statistics.filter_mode())


def test_package_reads(router):
    # Package quota/usage values are private operational data. Validate only
    # the documented shape/types and do not print the concrete values.
    settings = router.package.settings()
    status = router.package.status()

    _assert_mapping(settings)
    _assert_mapping(status)
    assert isinstance(settings.get("package_type"), str)
    assert isinstance(settings.get("data_used"), int)
    assert isinstance(status.get("status"), int)
