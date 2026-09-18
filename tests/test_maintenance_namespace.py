import pytest

from nr2301 import APIError, NR2301Client

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


def test_timed_reboot_uses_documented_get_method_and_preserves_raw_time():
    payload = {"enable": 0, "time": "0:0", "repeat": 128, "result": 0}
    client, session = authenticated_client(payload)

    assert client.maintenance.timed_reboot() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "router"
    assert kwargs["params"]["method"] == "router_get_timed_reboot"


def test_set_timed_reboot_writes_exact_fields_and_verifies_readback():
    client, session = authenticated_client(
        {"enable": 1, "time": "03:30", "repeat": 62, "result": 0},
        {"router": {"setting_response": "OK"}},
        {"enable": 0, "time": "23:58", "repeat": 63, "result": 0},
    )

    result = client.maintenance.set_timed_reboot(False, "23:58", 63)

    assert result["enable"] == 0
    assert result["time"] == "23:58"
    assert result["repeat"] == 63
    assert [call[0] for call in session.calls] == ["GET", "POST", "GET"]

    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["params"]["path"] == "router"
    assert write_kwargs["params"]["method"] == "router_set_timed_reboot"
    assert write_kwargs["json"] == {"enable": 0, "time": "23:58", "repeat": 63}


def test_set_timed_reboot_normalizes_unpadded_input_before_write():
    client, session = authenticated_client(
        {"enable": 1, "time": "3:30", "repeat": 62, "result": 0},
        {"router": {"setting_response": "OK"}},
        {"enable": 0, "time": "0:0", "repeat": 63, "result": 0},
    )

    result = client.maintenance.set_timed_reboot(False, "0:0", 63)

    assert result["time"] == "0:0"
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["json"] == {"enable": 0, "time": "00:00", "repeat": 63}


def test_set_timed_reboot_same_semantic_state_avoids_write_across_padding():
    current = {"enable": 0, "time": "0:0", "repeat": 63, "result": 0}
    client, session = authenticated_client(current)

    assert client.maintenance.set_timed_reboot(False, "00:00", 63) == current
    assert [call[0] for call in session.calls] == ["GET"]


@pytest.mark.parametrize("invalid", ["24:00", "23:60", "3:", "03:30:00", ""])
def test_set_timed_reboot_rejects_invalid_time(invalid):
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="H:M/HH:MM"):
        client.maintenance.set_timed_reboot(False, invalid, 1)

    assert session.calls == []


@pytest.mark.parametrize("invalid", [-1, 256])
def test_set_timed_reboot_rejects_out_of_range_repeat(invalid):
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="0 and 255"):
        client.maintenance.set_timed_reboot(False, "03:30", invalid)

    assert session.calls == []


def test_set_timed_reboot_rejects_invalid_types_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="enabled must be a bool"):
        client.maintenance.set_timed_reboot(0, "03:30", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="repeat must be an int"):
        client.maintenance.set_timed_reboot(False, "03:30", True)  # type: ignore[arg-type]

    assert session.calls == []


def test_set_timed_reboot_raises_when_semantic_readback_does_not_match():
    client, _ = authenticated_client(
        {"enable": 1, "time": "03:30", "repeat": 62, "result": 0},
        {"router": {"setting_response": "OK"}},
        {"enable": 1, "time": "3:30", "repeat": 62, "result": 0},
    )

    with pytest.raises(APIError) as exc_info:
        client.maintenance.set_timed_reboot(False, "23:58", 63)

    assert exc_info.value.method_id == "router/router_set_timed_reboot"
    assert exc_info.value.response["expected"] == {
        "enable": 0,
        "time": "23:58",
        "repeat": 63,
    }
    assert exc_info.value.response["actual"] == {
        "enable": 1,
        "time": "03:30",
        "repeat": 62,
    }


def test_backup_config_uses_bodyless_get_and_requires_rc_zero():
    payload = {
        "rc": 0,
        "path": "/var/volatile/config_bak/config_bak.bin",
    }
    client, session = authenticated_client(payload)

    assert client.maintenance.backup_config() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "router"
    assert kwargs["params"]["method"] == "router_backup_config"
    assert "json" not in kwargs


def test_backup_config_rejects_nonzero_rc_without_exposing_unknown_fields():
    client, _ = authenticated_client({"rc": 7, "path": "secret-bearing-value"})

    with pytest.raises(APIError) as exc_info:
        client.maintenance.backup_config()

    assert exc_info.value.method_id == "router/router_backup_config"
    assert exc_info.value.response == {"rc": 7}


def test_restart_web_server_accepts_empty_action_body_then_verifies_runtime():
    client, session = authenticated_client(
        {"boot_time": 100, "result": 0},
        ValueError("empty response"),
        {"boot_time": 102, "result": 0},
    )

    result = client.maintenance.restart_web_server(
        recovery_attempts=1,
        recovery_delay=0,
        initial_delay=0,
    )

    assert result["boot_time_before"] == 100
    assert result["boot_time_after"] == 102
    assert result["action_error"] == "ProtocolError"
    assert result["outage_observed"] is False

    assert [call[2]["params"]["method"] for call in session.calls] == [
        "get_runtime_info",
        "restart_web_server",
        "get_runtime_info",
    ]
    assert session.calls[1][0] == "GET"
    assert "json" not in session.calls[1][2]


def test_restart_web_server_rejects_unexpected_full_router_reboot():
    client, _ = authenticated_client(
        {"boot_time": 1000, "result": 0},
        ValueError("empty response"),
        {"boot_time": 3, "result": 0},
    )

    with pytest.raises(APIError) as exc_info:
        client.maintenance.restart_web_server(
            recovery_attempts=1,
            recovery_delay=0,
            initial_delay=0,
        )

    assert exc_info.value.method_id == "router/restart_web_server"
    assert exc_info.value.response["boot_time_before"] == 1000
    assert exc_info.value.response["boot_time_after"] == 3


def test_reboot_uses_bodyless_get_and_requires_boot_time_reset():
    client, session = authenticated_client(
        {"boot_time": 9000, "result": 0},
        ValueError("connection lost during reboot"),
        {"boot_time": 4, "result": 0},
    )

    result = client.maintenance.reboot(
        recovery_attempts=1,
        recovery_delay=0,
        initial_delay=0,
    )

    assert result["boot_time_before"] == 9000
    assert result["boot_time_after"] == 4
    assert result["action_error"] == "ProtocolError"

    assert [call[2]["params"]["method"] for call in session.calls] == [
        "get_runtime_info",
        "router_call_reboot",
        "get_runtime_info",
    ]
    assert session.calls[1][0] == "GET"
    assert "json" not in session.calls[1][2]


def test_reboot_raises_when_runtime_recovers_without_boot_reset():
    client, _ = authenticated_client(
        {"boot_time": 9000, "result": 0},
        {"result": 0},
        {"boot_time": 9002, "result": 0},
    )

    with pytest.raises(APIError) as exc_info:
        client.maintenance.reboot(
            recovery_attempts=1,
            recovery_delay=0,
            initial_delay=0,
        )

    assert exc_info.value.method_id == "router/router_call_reboot"
    assert exc_info.value.response["boot_time_before"] == 9000
    assert exc_info.value.response["boot_time_after"] == 9002


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("restart_web_server", {"action_timeout": 0}),
        ("restart_web_server", {"recovery_attempts": 0}),
        ("restart_web_server", {"recovery_delay": -1}),
        ("restart_web_server", {"recovery_timeout": 0}),
        ("restart_web_server", {"initial_delay": -1}),
        ("reboot", {"action_timeout": 0}),
    ],
)
def test_disruptive_maintenance_rejects_invalid_recovery_options(method_name, kwargs):
    client, session = authenticated_client()

    with pytest.raises(ValueError):
        getattr(client.maintenance, method_name)(**kwargs)

    assert session.calls == []
