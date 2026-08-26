import pytest

from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(*payloads):
    responses = [
        payload if isinstance(payload, FakeResponse) else FakeResponse(payload)
        for payload in payloads
    ]
    session = FakeSession(responses)
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


@pytest.mark.parametrize(
    ("helper_name", "path", "api_method"),
    [
        ("info", "router", "get_device_info"),
        ("runtime", "router", "get_runtime_info"),
        ("diagnostics", "router", "get_diag_info"),
        ("internet", "router", "get_diag_internet_info"),
        ("features", "router", "get_feature_list"),
        ("mac_info", "router", "get_mac_info"),
        ("ui_language", "router", "get_ui_language"),
        ("battery", "aoc", "get_bat_info"),
        ("sleep_wait_time", "aoc", "sleep_wait_time"),
    ],
)
def test_device_read_helpers_use_documented_get_methods(helper_name, path, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.device, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == path
    assert kwargs["params"]["method"] == api_method


def test_device_info_keeps_sensitive_identifier_fields_without_transforming():
    payload = {
        "ICCID": "synthetic-iccid",
        "IMEI": "synthetic-imei",
        "IMSI": "synthetic-imsi",
        "sn": "synthetic-serial",
        "result": 0,
    }
    client, _ = authenticated_client(payload)

    assert client.device.info() == payload


def test_device_internet_preserves_documented_raw_access_value():
    client, _ = authenticated_client({"access": 1})

    assert client.device.internet()["access"] == 1
