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
    ("helper_name", "api_method"),
    [
        ("traffic", "stat_get_common_data"),
        ("traffic_transport_status", "stat_get_traffic_transport_status"),
        ("filter_mode", "get_black_white_mode"),
        ("login_client_mac", "get_login_client_mac"),
    ],
)
def test_statistics_read_helpers_use_documented_get_methods(helper_name, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.statistics, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "statistics"
    assert kwargs["params"]["method"] == api_method


def test_clients_without_request_type_uses_bodyless_get_variant():
    payload = {
        "clients_info": [
            {
                "alias": "Synthetic client",
                "ip": "192.0.2.10",
                "mac": "02:00:00:00:00:01",
                "type": "WIFI",
            }
        ]
    }
    client, session = authenticated_client(payload)

    assert client.statistics.clients() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["method"] == "get_conn_clients_info"
    assert "json" not in kwargs


def test_clients_passes_advanced_request_type_through_exactly():
    payload = {"clients_info": []}
    client, session = authenticated_client(payload)

    assert client.statistics.clients(request_type="synthetic_view") == payload

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["json"] == {"request_type": "synthetic_view"}


def test_clients_validates_request_type_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="must not be empty"):
        client.statistics.clients(request_type="   ")
    with pytest.raises(TypeError, match="str or None"):
        client.statistics.clients(request_type=1)  # type: ignore[arg-type]

    assert session.calls == []


@pytest.mark.parametrize(
    ("helper_name", "request_type"),
    [
        ("active_clients", "get_active_users"),
        ("inactive_clients", "get_inactive_users"),
        ("allow_clients", "get_allow_users"),
        ("forbidden_clients", "get_forbidden_users"),
    ],
)
def test_normalized_client_helpers_use_exact_frontend_tokens(helper_name, request_type):
    payload = {"clients_info": []}
    client, session = authenticated_client(payload)

    helper = getattr(client.statistics, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "statistics"
    assert kwargs["params"]["method"] == "get_conn_clients_info"
    assert kwargs["json"] == {"request_type": request_type}


def test_normalized_client_view_rejects_unknown_token_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="unsupported normalized"):
        client.statistics.client_view("get_offline_users")  # type: ignore[arg-type]

    assert session.calls == []


def test_set_alias_uses_exact_payload():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.statistics.set_alias("02:00:00:00:00:01", "Lab client") == payload
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "set_alias"
    assert kwargs["json"] == {
        "mac": "02:00:00:00:00:01",
        "alias": "Lab client",
    }


def test_allow_and_forbidden_helpers_use_integer_enable_and_optional_alias():
    client, session = authenticated_client({"result": 0}, {"result": 0}, {"result": 0})

    client.statistics.set_allow("02:00:00:00:00:01", True, alias="Allowed")
    client.statistics.set_forbidden("02:00:00:00:00:02", True, alias="Blocked")
    client.statistics.set_forbidden("02:00:00:00:00:02", False)

    assert session.calls[0][2]["json"] == {
        "mac": "02:00:00:00:00:01",
        "enable": 1,
        "alias": "Allowed",
    }
    assert session.calls[1][2]["json"] == {
        "mac": "02:00:00:00:00:02",
        "enable": 1,
        "alias": "Blocked",
    }
    assert session.calls[2][2]["json"] == {
        "mac": "02:00:00:00:00:02",
        "enable": 0,
    }


def test_filter_clear_helpers_use_documented_contracts():
    client, session = authenticated_client({"result": 0}, {"result": 0}, {"statistics": {}})

    client.statistics.set_filter_mode("white")
    client.statistics.clear_offline_user("02:00:00:00:00:03")
    client.statistics.clear_traffic()

    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["params"]["method"] == "set_black_white_mode"
    assert session.calls[0][2]["json"] == {"mode": "white"}

    assert session.calls[1][0] == "POST"
    assert session.calls[1][2]["params"]["method"] == "clear_offline_user"
    assert session.calls[1][2]["json"] == {"mac": "02:00:00:00:00:03"}

    assert session.calls[2][0] == "GET"
    assert session.calls[2][2]["params"]["method"] == "stat_clear_common_data"
    assert "json" not in session.calls[2][2]


def test_statistics_mutation_helpers_validate_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="mode must"):
        client.statistics.set_filter_mode("grey")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mac must not be empty"):
        client.statistics.set_alias("", "x")
    with pytest.raises(TypeError, match="alias must be a str"):
        client.statistics.set_alias("02:00:00:00:00:01", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="enabled must be a bool"):
        client.statistics.set_forbidden("02:00:00:00:00:01", 1)  # type: ignore[arg-type]

    assert session.calls == []


def test_statistics_traffic_preserves_counter_values():
    payload = {
        "statistics": {
            "duration": 12,
            "rx_bytes": 100,
            "tx_bytes": 200,
            "rx_tx_bytes": 300,
            "total_rx_bytes": 1000,
            "total_tx_bytes": 2000,
        }
    }
    client, _ = authenticated_client(payload)

    assert client.statistics.traffic() == payload
