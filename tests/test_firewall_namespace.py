import pytest

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


@pytest.mark.parametrize(
    ("helper_name", "api_method"),
    [
        ("disable_info", "fw_get_disable_info"),
        ("dmz_info", "fw_get_dmz_info"),
        ("vpn_passthrough", "fw_get_vpn_passthrough"),
        ("admin_from_wan", "get_admin_from_wan"),
        ("ping_from_wan", "get_ping_from_wan"),
        ("port_forward", "get_port_forward"),
        ("port_trigger", "get_port_trigger"),
        ("url_filter", "get_url_filter"),
        ("ip_filter_mode_state", "ww_read_switch_mode_state"),
        ("port_filter_mode_state", "ww_read_switch_port_mode_state"),
        ("upnp_state", "ww_upnp_open_close_state"),
    ],
)
def test_firewall_read_helpers_use_live_verified_get_methods(helper_name, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.firewall, helper_name)
    assert helper() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "firewall"
    assert kwargs["params"]["method"] == api_method
    assert "json" not in kwargs


def test_firewall_reads_preserve_raw_values_without_semantic_remapping():
    payload = {
        "firewall": {
            "dmz_dest_ip": "192.168.",
            "setting_response": "RAW",
        }
    }
    client, _ = authenticated_client(payload)

    assert client.firewall.dmz_info() == payload


def test_firewall_list_reads_preserve_items_exactly():
    payload = {
        "result": 0,
        "settings": {
            "enable": 1,
            "items": [{"synthetic": "value"}],
        },
    }
    client, _ = authenticated_client(payload)

    assert client.firewall.port_forward() == payload
