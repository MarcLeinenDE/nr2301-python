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
