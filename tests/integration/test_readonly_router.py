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

    base_url = os.environ.get("NR2301_URL", "http://192.168.1.1")
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
    _assert_mapping(router.mobile.network_settings())


def test_lan_dns_reads(router):
    _assert_mapping(router.lan.address())
    _assert_mapping(router.lan.dns())


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
