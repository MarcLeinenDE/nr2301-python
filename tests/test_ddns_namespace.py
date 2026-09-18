from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(payload):
    session = FakeSession([FakeResponse(payload)])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def test_ddns_settings_uses_live_verified_getter():
    payload = {
        "result": 0,
        "enabled": "0",
        "service_name": "example",
        "username": "secret-bearing",
        "password": "secret-bearing",
    }
    client, session = authenticated_client(payload)

    assert client.ddns.settings() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "ddns"
    assert kwargs["params"]["method"] == "get_ddns"
    assert "json" not in kwargs
