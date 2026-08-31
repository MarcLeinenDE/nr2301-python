import hashlib

import pytest

from nr2301 import AuthenticationError, NR2301Client, ProtocolError

from conftest import FakeResponse, FakeSession


def test_login_performs_lockout_guard_challenge_and_establishes_session(monkeypatch):
    session = FakeSession([])

    def set_cookie():
        session.cookies.set("CGISID", "session-123")

    session.responses.extend([
        FakeResponse({"result": 0, "retry_times": 5, "remain_time": 0}),
        FakeResponse({"rand": "router-rand", "result": 0}),
        FakeResponse({"result": 3}, on_json=set_cookie),
    ])
    monkeypatch.setattr("nr2301.client.generate_user_id", lambda: "abc123xy")

    client = NR2301Client(
        "http://192.168.1.1",
        username="admin",
        password="secret",
        session=session,
    )

    assert client.login() == {"result": 3}
    assert client.authenticated is True
    assert client.session_id == "session-123"

    guard = session.calls[0]
    assert guard[0] == "POST"
    assert guard[2]["params"]["method"] == "get_retrytimes_and_time"
    assert guard[2]["json"] == {"type": "admin"}

    challenge = session.calls[1]
    assert challenge[0] == "POST"
    assert challenge[2]["params"]["method"] == "get_rand"
    assert challenge[2]["json"] == {"type": "admin", "user_id": "abc123xy"}

    login = session.calls[2]
    expected_digest = hashlib.md5(b"router-randsecret").hexdigest()
    assert login[2]["json"] == {
        "type": "admin",
        "username": "admin",
        "password": expected_digest,
        "user_id": "abc123xy",
    }


def test_login_aborts_when_router_reports_lockout_time():
    session = FakeSession([
        FakeResponse({"result": 0, "retry_times": 0, "remain_time": 30}),
    ])
    client = NR2301Client(password="secret", session=session)

    with pytest.raises(AuthenticationError, match="retry in 30 s"):
        client.login()

    assert len(session.calls) == 1
    assert client.authenticated is False


def test_login_aborts_before_last_remaining_attempt():
    session = FakeSession([
        FakeResponse({"result": 0, "retry_times": "1", "remain_time": "0"}),
    ])
    client = NR2301Client(password="secret", session=session)

    with pytest.raises(AuthenticationError, match="only 1 attempt"):
        client.login()

    assert len(session.calls) == 1
    assert client.authenticated is False


def test_login_failure_raises_typed_exception(monkeypatch):
    session = FakeSession([
        FakeResponse({"result": 0, "retry_times": 5, "remain_time": 0}),
        FakeResponse({"rand": "r", "result": 0}),
        FakeResponse({"result": 1}),
    ])
    monkeypatch.setattr("nr2301.client.generate_user_id", lambda: "abc123xy")
    client = NR2301Client(password="wrong", session=session)

    with pytest.raises(AuthenticationError) as exc:
        client.login()

    assert exc.value.result == 1
    assert "password error" in str(exc.value)
    assert client.authenticated is False


def test_login_requires_cgisid_cookie(monkeypatch):
    session = FakeSession([
        FakeResponse({"result": 0, "retry_times": 5, "remain_time": 0}),
        FakeResponse({"rand": "r", "result": 0}),
        FakeResponse({"result": 3}),
    ])
    monkeypatch.setattr("nr2301.client.generate_user_id", lambda: "abc123xy")
    client = NR2301Client(password="secret", session=session)

    with pytest.raises(ProtocolError):
        client.login()


def test_authenticated_call_requires_login():
    client = NR2301Client(password="secret", session=FakeSession([]))
    with pytest.raises(AuthenticationError):
        client.call("version", "get_ww_version")


def test_logout_clears_local_session_state():
    session = FakeSession([FakeResponse({"result": 0})])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True

    assert client.logout() == {"result": 0}
    assert client.authenticated is False
    assert client.session_id is None


def test_context_manager_logs_out_and_closes():
    session = FakeSession([FakeResponse({"result": 0})])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True

    with client:
        pass

    assert session.closed is True
    assert client.session_id is None
