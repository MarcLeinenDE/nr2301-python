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
    ("helper_name", "api_method"),
    [
        ("cell_info", "get_cell_info"),
        ("wan_info", "get_current_wan_info"),
        ("available_network_modes", "get_available_network_mode"),
        ("network_settings", "get_network_settings"),
    ],
)
def test_mobile_helpers_use_live_verified_get_methods(helper_name, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.mobile, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == api_method


def test_set_network_mode_validates_runtime_mode_and_verifies_readback():
    client, session = authenticated_client(
        {"network_modes": ["auto", "5g-sa"], "result": 0},
        {"network_settings": {"network_mode": "auto", "data_roaming": "0"}},
        {"result": 0},
        {"network_settings": {"network_mode": "5g-sa", "data_roaming": "0"}},
    )

    result = client.mobile.set_network_mode("5g-sa", verify_delay=0)

    assert result["network_mode"] == "5g-sa"
    assert [call[0] for call in session.calls] == ["GET", "GET", "POST", "GET"]
    _, _, write_kwargs = session.calls[2]
    assert write_kwargs["params"]["path"] == "cm"
    assert write_kwargs["params"]["method"] == "set_network_settings"
    assert write_kwargs["json"] == {"network_mode": "5g-sa"}


def test_set_network_mode_refuses_value_not_reported_by_router():
    client, session = authenticated_client(
        {"network_modes": ["auto", "lte"], "result": 0},
    )

    with pytest.raises(ValueError, match="not currently reported as available"):
        client.mobile.set_network_mode("5g-sa", verify_delay=0)

    assert len(session.calls) == 1
    assert session.calls[0][2]["params"]["method"] == "get_available_network_mode"


def test_set_network_mode_same_state_avoids_write():
    current = {"network_mode": "auto", "data_roaming": "0"}
    client, session = authenticated_client(
        {"network_modes": ["auto", "lte"], "result": 0},
        {"network_settings": current},
    )

    result = client.mobile.set_network_mode("auto", verify_delay=0)

    assert result == current
    assert [call[0] for call in session.calls] == ["GET", "GET"]


def test_set_data_roaming_writes_only_roaming_field_and_verifies():
    client, session = authenticated_client(
        {"network_settings": {"network_mode": "auto", "data_roaming": "0"}},
        {"result": 0},
        {"network_settings": {"network_mode": "auto", "data_roaming": "1"}},
    )

    result = client.mobile.set_data_roaming(True, verify_delay=0)

    assert result["data_roaming"] == "1"
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["params"]["method"] == "set_network_settings"
    assert write_kwargs["json"] == {"data_roaming": "1"}


def test_mobile_write_uses_readback_after_transport_failure():
    client, session = authenticated_client(
        {"network_settings": {"network_mode": "auto", "data_roaming": "0"}},
        FakeResponse({}, status_code=500),
        {"network_settings": {"network_mode": "auto", "data_roaming": "1"}},
    )

    result = client.mobile.set_data_roaming(True, verify_delay=0)

    assert result["data_roaming"] == "1"
    assert len(session.calls) == 3


def test_mobile_write_raises_when_exact_readback_does_not_match():
    client, _ = authenticated_client(
        {"network_modes": ["auto", "5g-sa"], "result": 0},
        {"network_settings": {"network_mode": "auto", "data_roaming": "0"}},
        {"result": 0},
        {"network_settings": {"network_mode": "auto", "data_roaming": "0"}},
    )

    with pytest.raises(APIError) as exc_info:
        client.mobile.set_network_mode(
            "5g-sa",
            verify_attempts=1,
            verify_delay=0,
        )

    assert exc_info.value.method_id == "cm/set_network_settings"
    assert exc_info.value.response["expected"] == "5g-sa"
    assert exc_info.value.response["actual"] == "auto"


def test_set_data_roaming_requires_bool_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="enabled must be a bool"):
        client.mobile.set_data_roaming("1")  # type: ignore[arg-type]

    assert session.calls == []
