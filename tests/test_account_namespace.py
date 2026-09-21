import pytest

from nr2301 import APIError, NR2301Client

from conftest import FakeResponse, FakeSession


_SYNTHETIC_PASSWORD = "Temporary9!"


def authenticated_client(*payloads):
    responses = [
        payload if isinstance(payload, FakeResponse) else FakeResponse(payload)
        for payload in payloads
    ]
    session = FakeSession(responses)
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="synthetic-current", session=session)
    client._authenticated = True
    return client, session


def test_account_info_uses_post_with_admin_type_and_current_session_id():
    client, session = authenticated_client(
        {"result": 0, "total_time": 300, "modified": 1}
    )

    result = client.account.info(timeout=7)

    assert result["result"] == 0
    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "account"
    assert kwargs["params"]["method"] == "get_info"
    assert kwargs["json"] == {
        "type": "admin",
        "session_id": "session-123",
    }
    assert kwargs["timeout"] == 7


def test_set_password_uses_exact_frontend_body_and_fresh_login(monkeypatch):
    client, session = authenticated_client({"result": 0})

    login_passwords = []

    def fake_login():
        login_passwords.append(client.password)
        client._authenticated = True
        session.cookies.set("CGISID", "new-session")
        return {"result": 3}

    monkeypatch.setattr(client, "login", fake_login)

    result = client.account.set_password(_SYNTHETIC_PASSWORD, timeout=8)

    assert result == {"result": 0}
    assert client.password == _SYNTHETIC_PASSWORD
    assert login_passwords == [_SYNTHETIC_PASSWORD]

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "account"
    assert kwargs["params"]["method"] == "set_info"
    assert kwargs["json"] == {
        "type": "admin",
        "session_id": "session-123",
        "password": _SYNTHETIC_PASSWORD,
    }
    assert "password_confirm" not in kwargs["json"]
    assert "old_password" not in kwargs["json"]


def test_set_password_can_skip_login_verification():
    client, session = authenticated_client({"result": 0})

    result = client.account.set_password(
        _SYNTHETIC_PASSWORD,
        verify_login=False,
    )

    assert result["result"] == 0
    assert client.password == _SYNTHETIC_PASSWORD
    assert len(session.calls) == 1


def test_set_password_rejects_firmware_error_without_echoing_secret():
    client, _ = authenticated_client({"result": -1001})

    with pytest.raises(APIError) as exc_info:
        client.account.set_password(
            _SYNTHETIC_PASSWORD,
            verify_login=False,
        )

    assert exc_info.value.method_id == "account/set_info"
    assert exc_info.value.response == {"result": -1001}
    assert _SYNTHETIC_PASSWORD not in str(exc_info.value)
    assert _SYNTHETIC_PASSWORD not in repr(exc_info.value.response)


@pytest.mark.parametrize(
    "password",
    [
        "",
        "1234",
        " " * 5,
        "äbcde",
        "x" * 33,
    ],
)
def test_set_password_validates_frontend_constraints_before_network(password):
    client, session = authenticated_client()

    with pytest.raises((TypeError, ValueError)):
        client.account.set_password(password)

    assert session.calls == []


def test_set_timeout_uses_string_value_and_same_set_info_contract():
    client, session = authenticated_client({"result": 0})

    result = client.account.set_timeout(900)

    assert result["result"] == 0
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "account"
    assert kwargs["params"]["method"] == "set_info"
    assert kwargs["json"] == {
        "type": "admin",
        "session_id": "session-123",
        "total_time": "900",
    }


@pytest.mark.parametrize("seconds", [0, 30, 120, 901, True, "300"])
def test_set_timeout_rejects_values_not_offered_by_stock_frontend(seconds):
    client, session = authenticated_client()

    with pytest.raises((TypeError, ValueError)):
        client.account.set_timeout(seconds)  # type: ignore[arg-type]

    assert session.calls == []
