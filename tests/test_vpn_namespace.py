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


def profile(index="0", *, name="Example", protocol="pptp", server="vpn.invalid", username="user"):
    return {
        "index": index,
        "vpn_name": name,
        "protocol_type": protocol,
        "vpn_server": server,
        "vpn_user_name": username,
        "vpn_user_password": "secret-from-router",
        "vpn_secure": "secret-from-router",
    }


def profile_response(*profiles, enabled="disable", active_index=""):
    return {
        "result": 0,
        "vpn_client_enable": enabled,
        "vpn_client_active_index": active_index,
        "vpn_clients": list(profiles),
    }


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


def test_vpn_profiles_uses_live_verified_getter():
    payload = profile_response()
    client, session = authenticated_client(payload)

    assert client.vpn.profiles() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == "get_vpn_clients"
    assert "json" not in kwargs


def test_set_enabled_same_state_avoids_write():
    payload = profile_response(enabled="disable")
    client, session = authenticated_client(payload)

    assert client.vpn.set_enabled(False) == payload
    assert len(session.calls) == 1


def test_set_enabled_writes_exact_token_and_verifies():
    before = profile_response(enabled="disable")
    after = profile_response(enabled="enable")
    client, session = authenticated_client(before, {"result": 0}, after)

    assert client.vpn.set_enabled(True) == after

    assert [call[0] for call in session.calls] == ["GET", "POST", "GET"]
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == "open_close_vpn_clients"
    assert kwargs["json"] == {"vpn_client_enable": "enable"}


def test_add_profile_writes_exact_body_and_returns_new_profile():
    added = profile(
        "3",
        name="SDK-VPN",
        protocol="l2tp/ipsec",
        server="vpn.example.invalid",
        username="sdk-user",
    )
    client, session = authenticated_client(
        profile_response(),
        {"result": 0},
        profile_response(added),
    )

    result = client.vpn.add_profile(
        name="SDK-VPN",
        protocol="l2tp/ipsec",
        server="vpn.example.invalid",
        username="sdk-user",
        password="sdk-password",
        secure="sdk-psk",
    )

    assert result == added
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["method"] == "add_vpn_client_item"
    assert kwargs["json"] == {
        "index": "-1",
        "vpn_name": "SDK-VPN",
        "protocol_type": "l2tp/ipsec",
        "vpn_server": "vpn.example.invalid",
        "vpn_user_name": "sdk-user",
        "vpn_user_password": "sdk-password",
        "vpn_secure": "sdk-psk",
    }


def test_add_profile_error_details_do_not_echo_secrets():
    client, _ = authenticated_client(
        profile_response(),
        {"result": 0},
        profile_response(),
    )

    with pytest.raises(APIError) as exc_info:
        client.vpn.add_profile(
            name="SDK-VPN",
            protocol="pptp",
            server="vpn.example.invalid",
            username="sdk-user",
            password="do-not-echo-password",
            secure="do-not-echo-psk",
        )

    details = repr(exc_info.value.response)
    assert "do-not-echo-password" not in details
    assert "do-not-echo-psk" not in details


def test_edit_profile_writes_full_body_and_verifies_public_fields():
    before = profile("2", name="Before")
    after = profile(
        "2",
        name="After",
        protocol="l2tp",
        server="edited.invalid",
        username="edited-user",
    )
    client, session = authenticated_client(
        profile_response(before),
        {"result": 0},
        profile_response(after),
    )

    result = client.vpn.edit_profile(
        "2",
        name="After",
        protocol="l2tp",
        server="edited.invalid",
        username="edited-user",
        password="new-password",
    )

    assert result == after
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["method"] == "edit_vpn_client_item"
    assert kwargs["json"] == {
        "index": "2",
        "vpn_name": "After",
        "protocol_type": "l2tp",
        "vpn_server": "edited.invalid",
        "vpn_user_name": "edited-user",
        "vpn_user_password": "new-password",
        "vpn_secure": "",
    }


def test_delete_profile_requires_disappearance_on_readback():
    before = profile("1")
    client, session = authenticated_client(
        profile_response(before),
        {"result": 0},
        profile_response(),
    )

    result = client.vpn.delete_profile(1)

    assert result["vpn_clients"] == []
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["method"] == "del_vpn_client_item"
    assert kwargs["json"] == {"index": "1"}


def test_set_profile_active_writes_exact_body_and_verifies_active_index():
    item = profile("4")
    client, session = authenticated_client(
        profile_response(item, active_index=""),
        {"result": 0},
        profile_response(item, active_index="4"),
    )

    result = client.vpn.set_profile_active("4", True)

    assert result["vpn_client_active_index"] == "4"
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["method"] == "active_vpn_client_item"
    assert kwargs["json"] == {"index": "4", "vpn_active": "active"}


def test_set_profile_active_accepts_disable_no_active_sentinel():
    item = profile("4")
    client, session = authenticated_client(
        profile_response(item, enabled="disable", active_index="disable"),
        {"result": 0},
        profile_response(item, enabled="enable", active_index="4"),
    )

    # The helper itself only owns the profile-active endpoint; the synthetic
    # final response models a firmware state where the profile becomes visible
    # as active.
    result = client.vpn.set_profile_active("4", True)

    assert result["vpn_client_active_index"] == "4"
    _, _, kwargs = session.calls[1]
    assert kwargs["json"] == {"index": "4", "vpn_active": "active"}


def test_set_profile_inactive_accepts_numeric_minus_one_sentinel():
    item = profile("4")
    client, session = authenticated_client(
        profile_response(item, active_index="4"),
        {"result": 0},
        {
            "result": 0,
            "vpn_client_enable": "disable",
            "vpn_client_active_index": -1,
            "vpn_clients": [item],
        },
    )

    result = client.vpn.set_profile_active(4, False)

    assert result["vpn_client_active_index"] == -1
    _, _, kwargs = session.calls[1]
    assert kwargs["json"] == {"index": "4", "vpn_active": "inactive"}


@pytest.mark.parametrize("protocol", ["wireguard", "", "PPTP"])
def test_add_profile_rejects_unverified_protocol_values(protocol):
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="protocol"):
        client.vpn.add_profile(
            name="SDK-VPN",
            protocol=protocol,  # type: ignore[arg-type]
            server="vpn.invalid",
            username="user",
            password="secret",
        )

    assert session.calls == []


def test_profile_index_must_be_numeric_and_existing_before_write():
    client, session = authenticated_client(profile_response())

    with pytest.raises(ValueError, match="does not exist"):
        client.vpn.delete_profile("5")

    assert len(session.calls) == 1
