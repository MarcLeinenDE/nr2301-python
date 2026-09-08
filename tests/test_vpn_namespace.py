from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(payload):
    session = FakeSession([FakeResponse(payload)])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def test_vpn_status_uses_live_verified_getter():
    payload = {"result": 0, "vpn_status": "synthetic-status"}
    client, session = authenticated_client(payload)

    assert client.vpn.status() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == "get_vpn_client_connect_status"
    assert "json" not in kwargs


def test_vpn_status_preserves_unknown_raw_status():
    payload = {"result": 0, "vpn_status": "future-status"}
    client, _ = authenticated_client(payload)

    assert client.vpn.status() == payload
