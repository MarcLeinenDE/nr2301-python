# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import pytest

from nr2301 import APIError, NR2301Client


if os.environ.get("NR2301_INTEGRATION") != "1":
    pytest.skip(
        "physical-router read-only tests require NR2301_INTEGRATION=1",
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


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        pytest.fail(f"{label} did not return an object")
    return value


def _optional_int(mapping: Mapping[str, Any], key: str, label: str) -> None:
    if key in mapping:
        value = mapping[key]
        if isinstance(value, bool) or not isinstance(value, int):
            pytest.fail(f"{label}.{key} was not an integer")


def _optional_str(mapping: Mapping[str, Any], key: str, label: str) -> None:
    if key in mapping and not isinstance(mapping[key], str):
        pytest.fail(f"{label}.{key} was not a string")


def test_device_mac_info_without_logging_identifiers(router):
    response = _mapping(router.device.mac_info(timeout=10.0), "router/get_mac_info")
    _optional_int(response, "result", "router/get_mac_info")

    for key in (
        "5g_mac",
        "eth_mac",
        "extender_mac",
        "guest_mac",
        "rndis_mac",
        "wifi_mac",
    ):
        _optional_str(response, key, "router/get_mac_info")

    print(
        "READONLY_ROUTER_MAC_INFO"
        f" fields_present={sum(key in response for key in ('5g_mac','eth_mac','extender_mac','guest_mac','rndis_mac','wifi_mac'))}"
        " sensitive_values_logged=False",
        flush=True,
    )


def test_statistics_login_client_mac_without_logging_identifier(router):
    response = _mapping(
        router.statistics.login_client_mac(timeout=10.0),
        "statistics/get_login_client_mac",
    )
    _optional_int(response, "result", "statistics/get_login_client_mac")
    _optional_str(response, "mac", "statistics/get_login_client_mac")

    print(
        "READONLY_LOGIN_CLIENT_MAC"
        f" mac_present={isinstance(response.get('mac'), str) and bool(response.get('mac'))}"
        " sensitive_value_logged=False",
        flush=True,
    )


def test_version_magic_number_shape_without_logging_value(router):
    response = _mapping(router.version.magic_number(), "version/get_magicnumber")
    _optional_int(response, "result", "version/get_magicnumber")
    _optional_str(response, "magic", "version/get_magicnumber")

    assert isinstance(response.get("magic"), str)
    print(
        "READONLY_MAGIC_NUMBER"
        " magic_present=True"
        " raw_value_logged=False",
        flush=True,
    )


def test_wifi_diagnostics_shape(router):
    response = _mapping(
        router.wifi.diagnostics(timeout=10.0),
        "wireless/get_diag_wifi_info",
    )
    for key in (
        "wifi_5g_pwd_lv",
        "wifi_dual_pwd_lv",
        "wifi_power",
        "wifi_pwd_lv",
        "wifi_st",
    ):
        _optional_int(response, key, "wireless/get_diag_wifi_info")
    _optional_str(response, "mode", "wireless/get_diag_wifi_info")

    print(
        "READONLY_WIFI_DIAGNOSTICS"
        f" mode_present={isinstance(response.get('mode'), str)}"
        " sensitive_values_logged=False",
        flush=True,
    )


def test_wifi_extender_config_without_logging_credentials(router):
    response = _mapping(
        router.wifi.extender_config(timeout=10.0),
        "wireless/get_extender_config",
    )
    _optional_int(response, "enable", "wireless/get_extender_config")
    _optional_str(response, "ssid", "wireless/get_extender_config")
    _optional_str(response, "key", "wireless/get_extender_config")

    print(
        "READONLY_WIFI_EXTENDER_CONFIG"
        f" enable_present={isinstance(response.get('enable'), int) and not isinstance(response.get('enable'), bool)}"
        f" ssid_present={isinstance(response.get('ssid'), str)}"
        f" key_present={isinstance(response.get('key'), str)}"
        " credential_values_logged=False",
        flush=True,
    )


def test_wifi_timed_off_status_shape(router):
    response = _mapping(
        router.wifi.timed_off_status(timeout=10.0),
        "wireless/wifi_get_timed_off_status",
    )
    _optional_int(response, "result", "wireless/wifi_get_timed_off_status")
    _optional_str(response, "status", "wireless/wifi_get_timed_off_status")

    assert isinstance(response.get("status"), str)
    print(
        "READONLY_WIFI_TIMED_OFF_STATUS"
        " status_present=True"
        " semantic_value_logged=False",
        flush=True,
    )


def test_sms_query_sdk_semantics_without_logging_ids(router):
    # Use the exact source/live-verified request tuple from nr2301-api.
    # The tested router previously returned resp=-2 for this query, while
    # resp=0 with comma-separated ids is the documented semantic success path.
    try:
        ids = router.sms.query_ids(
            message_type=4,
            read=2,
            location=0,
            timeout=10.0,
        )
    except APIError as exc:
        assert exc.method_id == "sms/sms.query"
        response = _mapping(exc.response, "sms/sms.query error response")
        sms = _mapping(response.get("sms"), "sms/sms.query error response.sms")
        resp = sms.get("resp")
        assert isinstance(resp, int) and not isinstance(resp, bool)
        print(
            "READONLY_SMS_QUERY"
            " semantic_success=False"
            f" resp={resp}"
            " ids_logged=False",
            flush=True,
        )
    else:
        assert all(isinstance(item, str) and item for item in ids)
        print(
            "READONLY_SMS_QUERY"
            " semantic_success=True"
            f" id_count={len(ids)}"
            " ids_logged=False",
            flush=True,
        )
