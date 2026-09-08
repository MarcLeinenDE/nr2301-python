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


def test_updated_status_uses_documented_get_contract():
    payload = {"fota_auto_upgrade_status": "0", "result": "0"}
    client, session = authenticated_client(payload)

    assert client.ota.updated_status() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "ota"
    assert kwargs["params"]["method"] == "get_updated_status"
    assert "json" not in kwargs


def test_query_state_uses_exact_type_1_post_contract():
    payload = {"response": "idle"}
    client, session = authenticated_client(payload)

    assert client.ota.query_state() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "ota"
    assert kwargs["params"]["method"] == "new_query"
    assert kwargs["json"] == {"type": 1}


def test_query_state_preserves_idle_as_raw_neutral_value():
    client, _ = authenticated_client({"response": "idle"})

    assert client.ota.query_state()["response"] == "idle"


def test_updated_status_preserves_raw_string_fields():
    payload = {"fota_auto_upgrade_status": "1", "result": "-1"}
    client, _ = authenticated_client(payload)

    assert client.ota.updated_status() == payload
