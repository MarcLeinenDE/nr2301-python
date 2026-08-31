import pytest

from nr2301 import APIError, NR2301Client, ProtocolError

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


@pytest.mark.parametrize(
    ("helper_name", "api_method"),
    [
        ("config", "wifi_get_ap_config"),
        ("timed_off_status", "wifi_get_timed_off_status"),
        ("wps", "wifi_get_wps_disable"),
        ("wps_status", "wps_status"),
        ("diagnostics", "get_diag_wifi_info"),
        ("extender_config", "get_extender_config"),
        ("extender_status", "get_extender_status"),
        ("scan", "wifi_scan"),
    ],
)
def test_wifi_get_helpers_use_documented_methods(helper_name, api_method):
    payload = (
        {"config": {}}
        if helper_name == "config"
        else {"wireless": {"wps_enable": "1"}}
        if helper_name == "wps"
        else {"synthetic": True}
    )
    client, session = authenticated_client(payload)

    helper = getattr(client.wifi, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "wireless"
    assert kwargs["params"]["method"] == api_method


def test_wifi_basic_info_uses_frontend_shaped_post():
    client, session = authenticated_client({"switch": "1"})

    assert client.wifi.basic_info() == {"switch": "1"}
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "wifi_get_basic_info"
    assert kwargs["json"] == {"sw_only": "1"}


def test_guest_enabled_and_separate_mode_use_verified_tokens():
    client, _ = authenticated_client(
        {"config": {"mode": "DUAL GUEST"}},
        {"config": {"mode": "2.4G 5G"}},
    )

    assert client.wifi.guest_enabled() is True
    assert client.wifi.uses_separate_ssids() is True


def test_mode_helpers_refuse_unknown_mode_semantics():
    client, session = authenticated_client({"config": {"mode": "FUTURE_MODE"}})

    with pytest.raises(ProtocolError, match="unsupported/unverified Wi-Fi mode"):
        client.wifi.guest_enabled()

    assert len(session.calls) == 1


def test_set_guest_enabled_preserves_guest_block_and_verifies_mode():
    guest = {
        "band_mode": "2.4G",
        "ssid": "Synthetic-Guest",
        "encryption": "psk-mixed+ccmp",
        "key": "synthetic-secret",
        "hidden": "0",
        "maxassoc": "10",
    }
    before = {"config": {"mode": "DUAL", "wifi_if_GUEST": guest}}
    after = {"config": {"mode": "DUAL GUEST", "wifi_if_GUEST": guest}}
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.set_guest_enabled(True, recovery_delay=0)

    assert result["config"]["mode"] == "DUAL GUEST"
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["params"]["method"] == "wifi_set_ap_config"
    assert write_kwargs["json"] == {
        "mode": "DUAL GUEST",
        "wifi_if_GUEST": guest,
    }


def test_set_guest_enabled_preserves_split_mode_when_disabling():
    guest = {"ssid": "Synthetic-Guest", "key": "synthetic-secret", "maxassoc": "9"}
    before = {"config": {"mode": "2.4G 5G GUEST", "wifi_if_GUEST": guest}}
    after = {"config": {"mode": "2.4G 5G", "wifi_if_GUEST": guest}}
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.set_guest_enabled(False, recovery_delay=0)

    assert result["config"]["mode"] == "2.4G 5G"
    assert session.calls[1][2]["json"]["mode"] == "2.4G 5G"


def test_set_guest_enabled_same_state_avoids_write():
    guest = {"ssid": "Synthetic-Guest", "key": "synthetic-secret"}
    before = {"config": {"mode": "DUAL GUEST", "wifi_if_GUEST": guest}}
    client, session = authenticated_client(before)

    result = client.wifi.set_guest_enabled(True, recovery_delay=0)

    assert result == before
    assert len(session.calls) == 1


def test_set_separate_ssids_preserves_guest_token_and_all_present_blocks():
    blocks = {
        "wifi_if_DUAL": {"ssid": "Combined", "key": "combined-secret"},
        "wifi_if_24G": {"ssid": "TwoFour", "key": "24-secret", "channel": "auto"},
        "wifi_if_5G": {"ssid": "Five", "key": "5-secret", "channel": "auto"},
        "wifi_if_GUEST": {"ssid": "Guest", "key": "guest-secret", "maxassoc": "10"},
    }
    before = {"config": {"mode": "DUAL GUEST", **blocks}}
    after = {"config": {"mode": "2.4G 5G GUEST", **blocks}}
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.set_separate_ssids(True, recovery_delay=0)

    assert result["config"]["mode"] == "2.4G 5G GUEST"
    payload = session.calls[1][2]["json"]
    assert payload["mode"] == "2.4G 5G GUEST"
    for key, block in blocks.items():
        assert payload[key] == block


def test_set_separate_ssids_uses_readback_after_transport_failure():
    guest = {"ssid": "Guest", "key": "guest-secret"}
    before = {"config": {"mode": "DUAL", "wifi_if_GUEST": guest}}
    after = {"config": {"mode": "2.4G 5G", "wifi_if_GUEST": guest}}
    client, session = authenticated_client(
        before,
        FakeResponse({}, status_code=500),
        after,
    )

    result = client.wifi.set_separate_ssids(True, recovery_delay=0)

    assert result["config"]["mode"] == "2.4G 5G"
    assert len(session.calls) == 3


def test_set_separate_ssids_requires_bool_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="separate must be a bool"):
        client.wifi.set_separate_ssids("yes")  # type: ignore[arg-type]

    assert session.calls == []


def test_set_guest_enabled_requires_bool_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="enabled must be a bool"):
        client.wifi.set_guest_enabled("1")  # type: ignore[arg-type]

    assert session.calls == []


def test_update_ap_section_preserves_current_block_and_verifies_changes():
    before = {
        "config": {
            "wifi_if_24G": {
                "ssid": "Example-24",
                "key": "unchanged-secret",
                "channel": "auto",
                "hidden": "0",
            }
        }
    }
    after = {
        "config": {
            "wifi_if_24G": {
                "ssid": "New-SSID",
                "key": "unchanged-secret",
                "channel": "auto",
                "hidden": "0",
            }
        }
    }
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.update_ap_section(
        "wifi_if_24G",
        {"ssid": "New-SSID"},
        recovery_delay=0,
    )

    assert result["ssid"] == "New-SSID"
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["params"]["method"] == "wifi_set_ap_config"
    assert write_kwargs["json"] == {
        "wifi_if_24G": {
            "ssid": "New-SSID",
            "key": "unchanged-secret",
            "channel": "auto",
            "hidden": "0",
        }
    }


def test_update_ap_section_same_state_avoids_write():
    before = {"config": {"wifi_if_GUEST": {"maxassoc": "10", "ssid": "Guest"}}}
    client, session = authenticated_client(before)

    result = client.wifi.update_ap_section(
        "wifi_if_GUEST",
        {"maxassoc": "10"},
        recovery_delay=0,
    )

    assert result["maxassoc"] == "10"
    assert len(session.calls) == 1


def test_update_ap_section_uses_readback_after_transport_failure():
    before = {"config": {"wifi_if_DUAL": {"ssid": "Old", "key": "secret"}}}
    after = {"config": {"wifi_if_DUAL": {"ssid": "New", "key": "secret"}}}
    client, session = authenticated_client(
        before,
        FakeResponse({}, status_code=500),
        after,
    )

    result = client.wifi.update_ap_section(
        "wifi_if_DUAL",
        {"ssid": "New"},
        recovery_delay=0,
    )

    assert result["ssid"] == "New"
    assert len(session.calls) == 3


def test_update_ap_section_raises_when_readback_does_not_match():
    before = {"config": {"wifi_if_5G": {"channel": "auto"}}}
    after = {"config": {"wifi_if_5G": {"channel": "auto"}}}
    client, _ = authenticated_client(before, {"result": 0}, after)

    with pytest.raises(APIError) as exc_info:
        client.wifi.update_ap_section(
            "wifi_if_5G",
            {"channel": "44"},
            recovery_attempts=1,
            recovery_delay=0,
        )

    assert exc_info.value.method_id == "wireless/wifi_set_ap_config"


def test_set_wps_enabled_writes_string_and_verifies():
    client, session = authenticated_client(
        {"wireless": {"wps_enable": "0"}},
        {"wireless": {"setting_response": "OK"}},
        {"wireless": {"wps_enable": "1"}},
    )

    result = client.wifi.set_wps_enabled(True, recovery_delay=0)

    assert result["wireless"]["wps_enable"] == "1"
    _, _, write_kwargs = session.calls[1]
    assert write_kwargs["json"] == {"wps_enable": "1"}


def test_set_wps_enabled_requires_bool_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="enabled must be a bool"):
        client.wifi.set_wps_enabled("1")  # type: ignore[arg-type]

    assert session.calls == []



def test_set_security_protected_mode_verifies_token_and_key():
    before = {
        "config": {
            "wifi_if_24G": {
                "ssid": "Synthetic",
                "encryption": "psk-mixed+ccmp",
                "key": "old-secret",
                "hidden": "0",
            }
        }
    }
    after = {
        "config": {
            "wifi_if_24G": {
                "ssid": "Synthetic",
                "encryption": "sae",
                "key": "new-synthetic-secret",
                "hidden": "0",
            }
        }
    }
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.set_security(
        "wifi_if_24G",
        "sae",
        "new-synthetic-secret",
        recovery_delay=0,
    )

    assert result["encryption"] == "sae"
    assert result["key"] == "new-synthetic-secret"
    payload = session.calls[1][2]["json"]["wifi_if_24G"]
    assert payload["ssid"] == "Synthetic"
    assert payload["encryption"] == "sae"
    assert payload["key"] == "new-synthetic-secret"


def test_set_security_open_mode_does_not_require_key_to_clear():
    before = {
        "config": {
            "wifi_if_5G": {
                "ssid": "Synthetic",
                "encryption": "psk-mixed+ccmp",
                "key": "retained-internal-secret",
            }
        }
    }
    after = {
        "config": {
            "wifi_if_5G": {
                "ssid": "Synthetic",
                "encryption": "none",
                "key": "retained-internal-secret",
            }
        }
    }
    client, session = authenticated_client(before, {"result": 0}, after)

    result = client.wifi.set_security("wifi_if_5G", "none", recovery_delay=0)

    assert result["encryption"] == "none"
    assert result["key"] == "retained-internal-secret"
    payload = session.calls[1][2]["json"]["wifi_if_5G"]
    assert payload["encryption"] == "none"
    assert payload["key"] == "retained-internal-secret"


def test_set_security_rejects_key_for_open_mode_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="open Wi-Fi mode does not accept a key"):
        client.wifi.set_security("wifi_if_DUAL", "none", "should-not-be-used")

    assert session.calls == []


def test_set_security_requires_key_for_protected_mode_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="non-empty key is required"):
        client.wifi.set_security("wifi_if_GUEST", "sae-mixed")

    assert session.calls == []


def test_set_security_rejects_unknown_token_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="unsupported/unverified Wi-Fi encryption token"):
        client.wifi.set_security(
            "wifi_if_24G",
            "future-security",  # type: ignore[arg-type]
            "synthetic-key",
        )

    assert session.calls == []



def test_wps_action_helpers_use_verified_contracts():
    client, session = authenticated_client(
        {"wireless": {"wps_call_pbc_result": "OK"}},
        {"wps_call_cancel_result": "OK"},
        {"wireless": {"wps_call_pin_result": "OK"}},
    )

    assert client.wifi.call_wps_pbc()["wireless"]["wps_call_pbc_result"] == "OK"
    assert client.wifi.call_wps_cancel()["wps_call_cancel_result"] == "OK"
    assert client.wifi.call_wps_pin("12345670")["wireless"]["wps_call_pin_result"] == "OK"

    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["params"]["method"] == "wifi_call_wps_pbc"
    assert session.calls[1][0] == "GET"
    assert session.calls[1][2]["params"]["method"] == "wifi_call_wps_cancel"
    assert session.calls[2][0] == "POST"
    assert session.calls[2][2]["params"]["method"] == "wifi_call_wps_pin"
    assert session.calls[2][2]["json"] == {"wps_enable": "1", "wps_pin": "12345670"}


def test_wps_pin_rejects_empty_value_before_network_access():
    client, session = authenticated_client()
    with pytest.raises(ValueError, match="pin must be a non-empty string"):
        client.wifi.call_wps_pin("")
    assert session.calls == []


def test_wps_action_rejects_non_ok_result():
    client, _ = authenticated_client({"wireless": {"wps_call_pbc_result": "FAIL"}})
    with pytest.raises(APIError, match="WPS action did not return"):
        client.wifi.call_wps_pbc()


def test_wps_action_helpers_accept_both_evidenced_envelopes():
    client, _ = authenticated_client(
        {"wps_call_pbc_result": "OK"},
        {"wireless": {"wps_call_cancel_result": "OK"}},
    )
    assert client.wifi.call_wps_pbc()["wps_call_pbc_result"] == "OK"
    assert client.wifi.call_wps_cancel()["wireless"]["wps_call_cancel_result"] == "OK"
