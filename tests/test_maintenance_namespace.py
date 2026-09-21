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


def test_download_config_backup_uses_stock_file_cgi_contract():
    client, session = authenticated_client(
        FakeResponse(content=b"opaque-secret-backup")
    )

    result = client.maintenance.download_config_backup(timeout=12)

    assert result == b"opaque-secret-backup"
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "http://zyxel.home/file.cgi"
    assert kwargs["params"] == {
        "Action": "Download",
        "file": "backup_config",
        "dl": "1",
    }
    assert kwargs["timeout"] == 12


def test_download_config_backup_rejects_empty_file():
    client, _ = authenticated_client(FakeResponse(content=b""))

    with pytest.raises(Exception, match="returned no data"):
        client.maintenance.download_config_backup()


def test_restore_config_backup_uploads_sequential_raw_chunks_and_verifies_reboot():
    client, session = authenticated_client(
        {"boot_time": 5000, "result": 0},
        FakeResponse(content=b"chunk-1-ok"),
        FakeResponse(status_code=503),
        {"boot_time": 7, "result": 0},
    )

    result = client.maintenance.restore_config_backup(
        b"ABCDEFGH",
        chunk_size=4,
        action_timeout=6,
        recovery_attempts=1,
        recovery_delay=0,
        recovery_timeout=2,
        initial_delay=0,
    )

    assert result["boot_time_before"] == 5000
    assert result["boot_time_after"] == 7
    assert result["uploaded_bytes"] == 8
    assert result["chunk_count"] == 2
    assert result["outage_observed"] is True
    assert result["action_error"] == "TransportError"

    assert [call[0] for call in session.calls] == ["GET", "POST", "POST", "GET"]

    first_upload = session.calls[1]
    second_upload = session.calls[2]
    for call in (first_upload, second_upload):
        _, url, kwargs = call
        assert url == "http://zyxel.home/file.cgi"
        assert kwargs["params"] == {
            "Action": "Upload",
            "file": "restore_config",
        }
        assert kwargs["headers"] == {
            "Content-Type": "application/octet-stream"
        }
        assert "files" not in kwargs
        assert "json" not in kwargs
        assert "Content-Range" not in kwargs["headers"]

    assert first_upload[2]["data"] == b"ABCD"
    assert second_upload[2]["data"] == b"EFGH"


def test_restore_config_backup_accepts_final_http_response_but_still_requires_reboot():
    client, _ = authenticated_client(
        {"boot_time": 5000, "result": 0},
        FakeResponse(content=b"ok"),
        {"boot_time": 6, "result": 0},
    )

    result = client.maintenance.restore_config_backup(
        b"ABCD",
        chunk_size=4,
        recovery_attempts=1,
        recovery_delay=0,
        initial_delay=0,
    )

    assert result["boot_time_after"] == 6
    assert result["outage_observed"] is False


def test_restore_config_backup_rejects_frontend_other_error_without_echoing_backup():
    client, _ = authenticated_client(
        {"boot_time": 5000, "result": 0},
        FakeResponse(content=b'{"system_err":" other error"}'),
    )

    secret = b"DO-NOT-ECHO-CONFIG-BYTES"
    with pytest.raises(APIError) as exc_info:
        client.maintenance.restore_config_backup(
            secret,
            chunk_size=len(secret),
            recovery_attempts=1,
            recovery_delay=0,
            initial_delay=0,
        )

    assert exc_info.value.method_id == "file.cgi/restore_config"
    assert secret.decode() not in repr(exc_info.value.response)


def test_restore_config_backup_requires_boot_time_reset():
    client, _ = authenticated_client(
        {"boot_time": 5000, "result": 0},
        FakeResponse(content=b"ok"),
        {"boot_time": 5001, "result": 0},
    )

    with pytest.raises(APIError) as exc_info:
        client.maintenance.restore_config_backup(
            b"ABCD",
            chunk_size=4,
            recovery_attempts=1,
            recovery_delay=0,
            initial_delay=0,
        )

    assert exc_info.value.method_id == "file.cgi/restore_config"
    assert exc_info.value.response["boot_time_before"] == 5000
    assert exc_info.value.response["boot_time_after"] == 5001


def test_restore_config_backup_validates_input_before_network_access(monkeypatch):
    import nr2301.namespaces.maintenance as maintenance_module

    client, session = authenticated_client()

    with pytest.raises(ValueError, match="must not be empty"):
        client.maintenance.restore_config_backup(b"")

    with pytest.raises(TypeError, match="bytes-like"):
        client.maintenance.restore_config_backup("nope")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="chunk_size"):
        client.maintenance.restore_config_backup(b"x", chunk_size=0)

    monkeypatch.setattr(maintenance_module, "_CONFIG_RESTORE_MAX_BYTES", 3)
    with pytest.raises(ValueError, match="200 MiB"):
        client.maintenance.restore_config_backup(b"four")

    assert session.calls == []


def test_factory_reset_uses_bodyless_get_switches_to_factory_password_and_verifies_boot(monkeypatch):
    client, session = authenticated_client(
        {"boot_time": 8000, "result": 0},
        FakeResponse(status_code=503),
        {"boot_time": 12, "result": 0},
    )

    login_passwords = []

    def fake_login():
        login_passwords.append(client.password)
        client._authenticated = True
        session.cookies.set("CGISID", "factory-session")
        return {"result": 3}

    monkeypatch.setattr(client, "login", fake_login)

    result = client.maintenance.factory_reset(
        "factory-secret",
        recovery_attempts=1,
        recovery_delay=0,
        initial_delay=0,
    )

    assert result["boot_time_before"] == 8000
    assert result["boot_time_after"] == 12
    assert result["outage_observed"] is True
    assert result["action_error"] == "TransportError"
    assert client.password == "factory-secret"
    assert login_passwords == ["factory-secret"]

    assert [call[2]["params"]["method"] for call in session.calls] == [
        "get_runtime_info",
        "router_call_rst_factory",
        "get_runtime_info",
    ]
    action = session.calls[1]
    assert action[0] == "GET"
    assert action[2]["params"]["path"] == "router"
    assert action[2]["params"]["method"] == "router_call_rst_factory"
    assert "json" not in action[2]


def test_factory_reset_rejects_missing_factory_password_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="must not be empty"):
        client.maintenance.factory_reset("")

    assert session.calls == []


def test_restore_config_backup_can_switch_to_restored_password_for_recovery(monkeypatch):
    client, session = authenticated_client(
        {"boot_time": 5000, "result": 0},
        FakeResponse(status_code=503),
        {"boot_time": 8, "result": 0},
    )

    login_passwords = []

    def fake_login():
        login_passwords.append(client.password)
        client._authenticated = True
        session.cookies.set("CGISID", "restored-session")
        return {"result": 3}

    monkeypatch.setattr(client, "login", fake_login)

    result = client.maintenance.restore_config_backup(
        b"ABCD",
        chunk_size=4,
        recovery_attempts=2,
        recovery_delay=0,
        initial_delay=0,
        recovery_password="original-secret",
    )

    assert result["boot_time_after"] == 8
    assert client.password == "original-secret"
    assert login_passwords == ["original-secret"]
    assert "original-secret" not in repr(result)


def test_restore_config_backup_rejects_empty_recovery_password_before_upload():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="recovery_password"):
        client.maintenance.restore_config_backup(
            b"ABCD",
            recovery_password="",
        )

    assert session.calls == []
