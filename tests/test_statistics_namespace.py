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
