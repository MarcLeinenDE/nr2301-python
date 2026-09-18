import pytest

from nr2301 import APIError, NR2301Client, ProtocolError
from nr2301.namespaces.mobile import MobileNamespace

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
        ("wan_settings", "get_wan_settings"),
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


def test_search_networks_uses_live_verified_operator_scan():
    payload = {"network_list": [], "result": 0}
    client, session = authenticated_client(payload)

    assert client.mobile.search_networks() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "util_wan"
    assert kwargs["params"]["method"] == "search_network"
    assert "json" not in kwargs


def test_network_select_mode_uses_live_verified_util_wan_getter():
    payload = {"nw_sel_mode": "auto", "result": 0}
    client, session = authenticated_client(payload)

    assert client.mobile.network_select_mode() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "util_wan"
    assert kwargs["params"]["method"] == "get_network_select_mode"
    assert "json" not in kwargs


@pytest.mark.parametrize(
    ("helper_name", "api_method"),
    [
        ("carrier_aggregation_info", "get_ca_info"),
        ("radio_metrics", "query_eng_info"),
    ],
)
def test_radio_diagnostics_use_required_one_member_multicall(helper_name, api_method):
    member = {"synthetic": "preserve-me"}
    client, session = authenticated_client({"responses": [member]})

    helper = getattr(client.mobile, helper_name)
    assert helper() == member

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    assert kwargs["json"] == {
        "requests": [{"path": "cm", "method": api_method}]
    }
    assert "data" not in kwargs["json"]["requests"][0]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"responses": []},
        {"responses": [{"first": True}, {"second": True}]},
        {"responses": ["not-an-object"]},
    ],
)
def test_radio_diagnostics_reject_malformed_multicall_envelopes(payload):
    client, _ = authenticated_client(payload)

    with pytest.raises(ProtocolError):
        client.mobile.radio_metrics()


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


def test_disconnect_mobile_uses_bodyless_get():
    client, session = authenticated_client({"result": 0})

    assert client.mobile.disconnect_mobile() == {"result": 0}

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == "disconnect"
    assert "json" not in kwargs


def test_connect_mobile_uses_bodyless_get():
    client, session = authenticated_client({"result": 0})

    assert client.mobile.connect_mobile() == {"result": 0}

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == "connect"
    assert "json" not in kwargs


def test_reconnect_mobile_recovers_and_requires_connected_readback():
    client, session = authenticated_client(
        {"result": 0},
        {"contextlist": [{"connection_status": 0}]},
        {"result": 0},
        {"contextlist": [{"connection_status": 1, "internet_status": 1}]},
        {"contextlist": [{"connection_status": 1, "internet_status": 1}]},
    )

    result = client.mobile.reconnect_mobile(
        recovery_attempts=1,
        recovery_delay=0,
    )

    assert result["contextlist"][0]["connection_status"] == 1
    assert [call[2]["params"]["method"] for call in session.calls] == [
        "disconnect",
        "get_current_wan_info",
        "connect",
        "get_current_wan_info",
        "get_current_wan_info",
    ]


def test_reconnect_mobile_treats_transport_failure_as_inconclusive_then_recovers():
    client, session = authenticated_client(
        FakeResponse({}, status_code=500),
        {"contextlist": [{"connection_status": 0}]},
        FakeResponse({}, status_code=500),
        {"contextlist": [{"connection_status": 1}]},
        {"contextlist": [{"connection_status": 1}]},
    )

    result = client.mobile.reconnect_mobile(
        recovery_attempts=1,
        recovery_delay=0,
    )

    assert result["contextlist"][0]["connection_status"] == 1
    assert len(session.calls) == 5


@pytest.mark.parametrize(
    "status",
    ["0", 0, "1", 1],
)
def test_wan_connection_status_parses_numeric_strings_and_ints(status):
    expected = int(status) == 1
    assert (
        MobileNamespace._wan_connected({"contextlist": [{"connection_status": status}]})
        is expected
    )


def test_select_network_auto_writes_exact_body_and_verifies_mode():
    client, session = authenticated_client(
        {"response": {"setting_response": "OK"}},
        {"contextlist": [{"connection_status": 1}]},
        {"nw_sel_mode": "auto", "result": 0},
    )

    result = client.mobile.select_network(
        "auto",
        recovery_attempts=1,
        recovery_delay=0,
    )

    assert result["nw_sel_mode"] == "auto"
    assert [call[2]["params"]["method"] for call in session.calls] == [
        "select_network",
        "get_current_wan_info",
        "get_network_select_mode",
    ]
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["params"]["path"] == "util_wan"
    assert session.calls[0][2]["json"] == {"network_param": "auto"}


def test_select_network_manual_value_is_passed_through_without_inventing_identifier():
    client, session = authenticated_client(
        {"response": {"setting_response": "OK"}},
        {"contextlist": [{"connection_status": 1}]},
        {"nw_sel_mode": "manual", "result": 0},
    )

    result = client.mobile.select_network(
        "SCAN-RETURNED-OPAQUE-VALUE",
        recovery_attempts=1,
        recovery_delay=0,
    )

    assert result["nw_sel_mode"] == "manual"
    assert session.calls[0][2]["json"] == {
        "network_param": "SCAN-RETURNED-OPAQUE-VALUE"
    }


def test_select_network_expected_mode_mismatch_raises_api_error():
    client, _ = authenticated_client(
        {"response": {"setting_response": "OK"}},
        {"contextlist": [{"connection_status": 1}]},
        {"nw_sel_mode": "manual", "result": 0},
    )

    with pytest.raises(APIError) as exc_info:
        client.mobile.select_network(
            "auto",
            recovery_attempts=1,
            recovery_delay=0,
        )

    assert exc_info.value.method_id == "util_wan/select_network"
    assert exc_info.value.response["expected_mode"] == "auto"
    assert exc_info.value.response["actual_mode"] == "manual"


def test_select_network_rejects_empty_parameter_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="must not be empty"):
        client.mobile.select_network("")

    assert session.calls == []
