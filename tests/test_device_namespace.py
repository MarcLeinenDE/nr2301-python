import pytest

from nr2301 import APIError, NR2301Client

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


def test_set_sleep_wait_time_writes_documented_field_and_verifies_readback():
    client, session = authenticated_client(
        {"result": 30},
        {"result": 0},
        {"result": 20},
    )

    result = client.device.set_sleep_wait_time(20)

    assert result == {"result": 20}
    assert [call[0] for call in session.calls] == ["GET", "POST", "GET"]
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["params"]["path"] == "aoc"
    assert write_kwargs["params"]["method"] == "set_sleep_wait_time"
    assert write_kwargs["json"] == {"time": 20}


def test_set_sleep_wait_time_same_state_avoids_write():
    client, session = authenticated_client({"result": 30})

    result = client.device.set_sleep_wait_time(30)

    assert result == {"result": 30}
    assert [call[0] for call in session.calls] == ["GET"]


@pytest.mark.parametrize("invalid", [-1, 1, 15, 50, 61])
def test_set_sleep_wait_time_rejects_unverified_values(invalid):
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="0, 10, 20, 30, 40 or 60"):
        client.device.set_sleep_wait_time(invalid)

    assert session.calls == []


def test_set_sleep_wait_time_rejects_bool_and_non_int():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="minutes must be an int"):
        client.device.set_sleep_wait_time(True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="minutes must be an int"):
        client.device.set_sleep_wait_time("30")  # type: ignore[arg-type]

    assert session.calls == []


def test_set_sleep_wait_time_raises_when_readback_does_not_match():
    client, _ = authenticated_client(
        {"result": 30},
        {"result": 0},
        {"result": 30},
    )

    with pytest.raises(APIError) as exc_info:
        client.device.set_sleep_wait_time(20)

    assert exc_info.value.method_id == "aoc/set_sleep_wait_time"
    assert exc_info.value.response == {"expected": 20, "actual": 30}
