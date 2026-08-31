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


@pytest.mark.parametrize(
    ("helper", "args", "method_name", "expected_body"),
    [
        ("provide_pin", ("1234",), "provide_pin", {"pin_puk": {"pin": "1234"}}),
        ("enable_pin", ("1234",), "enable_pin", {"pin_puk": {"pin": "1234"}}),
        ("disable_pin", ("1234",), "disable_pin", {"pin_puk": {"pin": "1234"}}),
        (
            "change_pin",
            ("1234", "5678"),
            "change_pin",
            {"pin_puk": {"pin": "1234", "new_pin": "5678"}},
        ),
        (
            "reset_pin_using_puk",
            ("12345678", "5678"),
            "reset_pin_using_puk",
            {"pin_puk": {"puk": "12345678", "new_pin": "5678"}},
        ),
    ],
)
def test_sim_mutation_helpers_use_exact_frontend_payloads(helper, args, method_name, expected_body):
    client, session = authenticated_client({"response": {"setting_response": "UNKNOWN"}})

    result = getattr(client.sim, helper)(*args, protect_retries=False)
    assert result == {"response": {"setting_response": "UNKNOWN"}}

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "sim"
    assert kwargs["params"]["method"] == method_name
    assert kwargs["json"] == expected_body


def test_sim_retry_guard_refuses_final_pin_attempt_without_secret_in_error():
    client, session = authenticated_client(
        {"pin_puk": {"pin_attempts": 1, "puk_attempts": 10}},
    )

    from nr2301 import APIError

    with pytest.raises(APIError) as exc_info:
        client.sim.enable_pin("8765")

    assert "8765" not in str(exc_info.value)
    assert exc_info.value.response == {"attempt_field": "pin_attempts", "attempts": 1}
    assert len(session.calls) == 1


def test_sim_retry_guard_allows_write_when_attempt_budget_is_safe():
    client, session = authenticated_client(
        {"pin_puk": {"pin_attempts": 3, "puk_attempts": 10}},
        {"response": {"setting_response": "UNKNOWN"}},
    )

    client.sim.disable_pin("1234")

    assert len(session.calls) == 2
    assert session.calls[1][2]["json"] == {"pin_puk": {"pin": "1234"}}


def test_sim_secret_validation_only_applies_source_verified_maximum():
    client, _ = authenticated_client()

    with pytest.raises(ValueError, match="maximum length of 8"):
        client.sim.provide_pin("123456789", protect_retries=False)
    with pytest.raises(ValueError, match="must not be empty"):
        client.sim.provide_pin("", protect_retries=False)
