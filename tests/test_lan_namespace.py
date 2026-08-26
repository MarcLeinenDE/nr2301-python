from __future__ import annotations

import pytest

from nr2301 import NR2301Client
from nr2301.exceptions import APIError, ProtocolError

from conftest import FakeResponse, FakeSession


def authenticated_client(responses):
    session = FakeSession([FakeResponse(payload, status_code=status) for payload, status in responses])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def dhcp_payload(**overrides):
    values = {
        "disabled": "0",
        "lan_ip": "192.168.1.1",
        "lan_netmask": "255.255.255.0",
        "start": "192.168.1.100",
        "end": "192.168.1.200",
        "leasetime": "86400",
        "mtu": "1500",
        "dnsmode": "auto",
        "dns1": "",
        "dns2": "",
        "ipv6dns1": "",
        "ipv6dns2": "",
    }
    values.update(overrides)
    return {"dhcp": values}


def test_lan_read_helpers_use_live_verified_get_methods():
    combined = dhcp_payload()
    address = {"router": {"lan_ip": "192.168.1.1", "lan_netmask": "255.255.255.0"}}
    client, session = authenticated_client(
        [(combined, 200), (combined, 200), (combined, 200), (address, 200)]
    )

    assert client.lan.settings() == combined
    assert client.lan.dhcp()["start"] == "192.168.1.100"
    assert client.lan.dns() == {
        "dnsmode": "auto",
        "dns1": "",
        "dns2": "",
        "ipv6dns1": "",
        "ipv6dns2": "",
    }
    assert client.lan.address() == address

    assert [call[0] for call in session.calls] == ["GET", "GET", "GET", "GET"]
    assert session.calls[0][2]["params"]["method"] == "router_get_dhcp_settings_comb"
    assert session.calls[3][2]["params"]["method"] == "router_get_lan_ip"


def test_set_dns_preserves_combined_settings_and_verifies_readback():
    before = dhcp_payload()
    after = dhcp_payload(
        dnsmode="manual",
        dns1="1.1.1.1",
        dns2="1.0.0.1",
        ipv6dns1="2606:4700:4700::1111",
        ipv6dns2="2606:4700:4700::1001",
    )
    client, session = authenticated_client(
        [(before, 200), ({"responses": [{"result": 0}]}, 200), (after, 200)]
    )

    result = client.lan.set_dns(
        "1.1.1.1",
        "1.0.0.1",
        ipv6_primary="2606:4700:4700::1111",
        ipv6_secondary="2606:4700:4700::1001",
        recovery_attempts=1,
    )

    assert result == {
        "dnsmode": "manual",
        "dns1": "1.1.1.1",
        "dns2": "1.0.0.1",
        "ipv6dns1": "2606:4700:4700::1111",
        "ipv6dns2": "2606:4700:4700::1001",
    }

    method, _, kwargs = session.calls[1]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    member = kwargs["json"]["requests"][0]
    assert member["path"] == "router"
    assert member["method"] == "router_set_dhcp_settings_comb"
    assert member["timeout"] == 30

    written = member["data"]
    assert written["lan_ip"] == "192.168.1.1"
    assert written["start"] == "192.168.1.100"
    assert written["mtu"] == "1500"
    assert written["dnsmode"] == "manual"
    assert written["dns1"] == "1.1.1.1"


def test_set_dns_uses_readback_even_when_write_transport_fails():
    before = dhcp_payload()
    after = dhcp_payload(dnsmode="manual", dns1="9.9.9.9")
    client, _ = authenticated_client([(before, 200), ({}, 500), (after, 200)])

    assert client.lan.set_dns("9.9.9.9", recovery_attempts=1)["dns1"] == "9.9.9.9"


def test_set_dns_auto_clears_dns_fields_and_verifies():
    before = dhcp_payload(
        dnsmode="manual",
        dns1="1.1.1.1",
        dns2="1.0.0.1",
        ipv6dns1="2606:4700:4700::1111",
        ipv6dns2="2606:4700:4700::1001",
    )
    after = dhcp_payload()
    client, session = authenticated_client(
        [(before, 200), ({"responses": [{"result": 0}]}, 200), (after, 200)]
    )

    assert client.lan.set_dns_auto(recovery_attempts=1)["dnsmode"] == "auto"
    written = session.calls[1][2]["json"]["requests"][0]["data"]
    assert written["dnsmode"] == "auto"
    assert written["dns1"] == ""
    assert written["dns2"] == ""
    assert written["ipv6dns1"] == ""
    assert written["ipv6dns2"] == ""


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        (("not-an-ip",), {}),
        (("2001:db8::1",), {}),
        (("1.1.1.1", "2001:db8::1"), {}),
        (("1.1.1.1",), {"ipv6_primary": "1.0.0.1"}),
    ],
)
def test_set_dns_rejects_wrong_address_family(args, kwargs):
    client, session = authenticated_client([])

    with pytest.raises(ValueError):
        client.lan.set_dns(*args, **kwargs)

    assert session.calls == []


def test_set_dns_refuses_partial_combined_object():
    incomplete = dhcp_payload()
    del incomplete["dhcp"]["mtu"]
    client, session = authenticated_client([(incomplete, 200)])

    with pytest.raises(ProtocolError, match="missing required fields: mtu"):
        client.lan.set_dns("1.1.1.1", recovery_attempts=1)

    assert len(session.calls) == 1


def test_set_dns_raises_api_error_when_readback_does_not_match():
    before = dhcp_payload()
    unchanged = dhcp_payload()
    client, _ = authenticated_client(
        [(before, 200), ({"responses": [{"result": 0}]}, 200), (unchanged, 200)]
    )

    with pytest.raises(APIError) as exc_info:
        client.lan.set_dns("1.1.1.1", recovery_attempts=1)

    assert exc_info.value.method_id == "router/router_set_dhcp_settings_comb"
    assert exc_info.value.response["expected"]["dns1"] == "1.1.1.1"
    assert exc_info.value.response["actual"]["dnsmode"] == "auto"
