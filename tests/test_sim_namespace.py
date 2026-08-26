import pytest

from nr2301 import NR2301Client, ProtocolError

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


def test_sim_status_uses_live_verified_get_method():
    payload = {
        "pin_puk": {
            "pin_attempts": 3,
            "pin_enabled": 1,
            "pin_status": 5,
            "puk_attempts": 10,
            "sim_status": 1,
        },
        "response": {"setting_response": "OK"},
    }
    client, session = authenticated_client(payload)

    assert client.sim.status() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "sim"
    assert kwargs["params"]["method"] == "get_sim_status"


def test_sim_summary_uses_documented_endpoint_scoped_labels():
    payload = {
        "pin_puk": {
            "pin_attempts": 3,
            "pin_enabled": 1,
            "pin_status": 5,
            "puk_attempts": 10,
            "sim_status": 1,
        }
    }
    client, _ = authenticated_client(payload)

    assert client.sim.summary() == {
        "sim_status": 1,
        "sim_status_text": "SIM present",
        "pin_status": 5,
        "pin_status_text": "Ready",
        "pin_enabled": 1,
        "pin_enabled_text": "PIN protection enabled",
        "pin_attempts": 3,
        "puk_attempts": 10,
    }


def test_sim_summary_preserves_unknown_raw_values():
    payload = {
        "pin_puk": {
            "pin_enabled": 7,
            "pin_status": 99,
            "sim_status": 42,
        }
    }
    client, _ = authenticated_client(payload)

    summary = client.sim.summary()
    assert summary["sim_status"] == 42
    assert summary["sim_status_text"] == "Unknown (42)"
    assert summary["pin_status_text"] == "Unknown (99)"
    assert summary["pin_enabled_text"] == "Unknown (7)"


def test_sim_status_requires_pin_puk_object():
    client, _ = authenticated_client({"response": {"setting_response": "OK"}})

    with pytest.raises(ProtocolError, match="pin_puk object"):
        client.sim.status()
