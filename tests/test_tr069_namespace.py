from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(payload):
    session = FakeSession([FakeResponse(payload)])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def test_tr069_config_uses_live_verified_getter():
    payload = {"result": 0, "acs_url": "https://acs.invalid", "enable": 0}
    client, session = authenticated_client(payload)

    assert client.tr069.config() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "tr069"
    assert kwargs["params"]["method"] == "get_config"
    assert "json" not in kwargs


def test_tr069_xmpp_config_uses_live_verified_getter():
    payload = {"result": 0, "enable": 0, "server": []}
    client, session = authenticated_client(payload)

    assert client.tr069.xmpp_config() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "tr069"
    assert kwargs["params"]["method"] == "get_xmpp_config"
    assert "json" not in kwargs
