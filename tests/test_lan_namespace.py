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


def test_static_reservations_uses_live_verified_getter_and_preserves_raw_response():
    payload = {
        "synthetic_nested_shape": [
            {"unknown_future_field": "preserve-me"},
        ],
        "result": 0,
    }
    client, session = authenticated_client([(payload, 200)])

    assert client.lan.static_reservations() == payload

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "router"
    assert kwargs["params"]["method"] == "router_get_dhcp_static_ip"
    assert "json" not in kwargs


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

    method, _, kwargs = session.calls[2]
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


def test_legacy_dhcp_settings_uses_verified_one_member_multicall():
    member = {"dhcp": {"disabled": "0", "limit": "10"}}
    client, session = authenticated_client([({"responses": [{"data": member}]}, 200)])

    assert client.lan.legacy_dhcp_settings() == member

    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    assert kwargs["json"] == {
        "requests": [{"path": "router", "method": "router_get_dhcp_settings"}]
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"responses": []},
        {"responses": ["not-an-object"]},
        {"responses": [{}]},
        {"responses": [{"data": "not-an-object"}]},
    ],
)
def test_legacy_dhcp_settings_rejects_malformed_multicall(payload):
    client, _ = authenticated_client([(payload, 200)])

    with pytest.raises(ProtocolError):
        client.lan.legacy_dhcp_settings()



def test_set_dhcp_settings_writes_complete_multicall_object_and_verifies():
    before = dhcp_payload()
    after = dhcp_payload(leasetime="43200")
    client, session = authenticated_client(
        [(before, 200), ({"responses": [{"result": 0}]}, 200), (after, 200)]
    )

    requested = dict(after["dhcp"])
    result = client.lan.set_dhcp_settings(requested, recovery_attempts=1)

    assert result["leasetime"] == "43200"
    method, _, kwargs = session.calls[1]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    member = kwargs["json"]["requests"][0]
    assert member["path"] == "router"
    assert member["method"] == "router_set_dhcp_settings_comb"
    assert member["timeout"] == 30
    assert member["data"] == requested
    assert set(member["data"]) == {
        "disabled",
        "lan_ip",
        "lan_netmask",
        "start",
        "end",
        "leasetime",
        "mtu",
        "dnsmode",
        "dns1",
        "dns2",
        "ipv6dns1",
        "ipv6dns2",
    }


def test_set_dhcp_settings_uses_readback_after_transport_failure():
    before = dhcp_payload()
    after = dhcp_payload(mtu="1499")
    client, _ = authenticated_client(
        [(before, 200), ({}, 500), (after, 200)]
    )

    result = client.lan.set_dhcp_settings(
        dict(after["dhcp"]),
        recovery_attempts=1,
    )

    assert result["mtu"] == "1499"


def test_set_dhcp_settings_rejects_partial_or_non_string_fields():
    incomplete = dict(dhcp_payload()["dhcp"])
    incomplete.pop("mtu")
    client, session = authenticated_client([])

    with pytest.raises(ProtocolError, match="missing required fields"):
        client.lan.set_dhcp_settings(incomplete)

    wrong_type = dict(dhcp_payload()["dhcp"])
    wrong_type["mtu"] = 1500
    with pytest.raises(TypeError, match="mtu must be a str"):
        client.lan.set_dhcp_settings(wrong_type)

    assert session.calls == []


def test_static_reservation_list_normalizes_verified_item_shape():
    payload = {
        "dhcp": {
            "cnt": 1,
            "data": [
                {
                    "index": 0,
                    "mac": "02:AA:BB:CC:DD:EE",
                    "ip": "192.0.2.10",
                }
            ],
        }
    }
    client, _ = authenticated_client([(payload, 200)])

    assert client.lan.static_reservation_list() == [
        {
            "index": 0,
            "mac": "02:aa:bb:cc:dd:ee",
            "ip": "192.0.2.10",
        }
    ]


def test_set_static_reservations_uses_multicall_and_exact_readback():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    before = {"dhcp": {"cnt": 0, "data": []}}
    expected_item = {
        "index": 0,
        "mac": "02:00:00:00:00:01",
        "ip": "192.168.1.254",
    }
    after = {"dhcp": {"cnt": 1, "data": [expected_item]}}
    client, session = authenticated_client(
        [
            (address, 200),
            (before, 200),
            ({"responses": [{"result": 0}]}, 200),
            (after, 200),
        ]
    )

    result = client.lan.set_static_reservations(
        [expected_item],
        recovery_attempts=1,
    )

    assert result == [expected_item]
    method, _, kwargs = session.calls[1]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    member = kwargs["json"]["requests"][0]
    assert member == {
        "path": "router",
        "method": "router_set_dhcp_static_ip",
        "data": {"data": [expected_item]},
        "timeout": 30,
    }


def test_set_static_reservations_recovers_after_write_transport_failure():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    before = {"dhcp": {"cnt": 0, "data": []}}
    expected_item = {
        "index": 0,
        "mac": "02:00:00:00:00:01",
        "ip": "192.168.1.254",
    }
    after = {"dhcp": {"cnt": 1, "data": [expected_item]}}
    client, _ = authenticated_client(
        [(address, 200), (before, 200), ({}, 500), (after, 200)]
    )

    assert client.lan.set_static_reservations(
        [expected_item],
        recovery_attempts=1,
    ) == [expected_item]


@pytest.mark.parametrize(
    "item",
    [
        {"index": "10", "mac": "02:00:00:00:00:01", "ip": "192.0.2.10"},
        {"index": "0", "mac": "invalid", "ip": "192.0.2.10"},
        {"index": "0", "mac": "02:00:00:00:00:01", "ip": "not-an-ip"},
    ],
)
def test_set_static_reservations_rejects_invalid_items_before_network(item):
    client, session = authenticated_client([])

    with pytest.raises((TypeError, ValueError)):
        client.lan.set_static_reservations([item])

    assert session.calls == []


def test_set_address_legacy_force_executes_same_state_setter_and_readback():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    client, session = authenticated_client(
        [(address, 200), ({"router": {"setting_response": "OK"}}, 200), (address, 200)]
    )

    result = client.lan.set_address_legacy(
        "192.168.1.1",
        "255.255.255.0",
        force=True,
        recovery_attempts=1,
    )

    assert result == address
    assert [call[0] for call in session.calls] == ["GET", "POST", "GET"]
    _, _, kwargs = session.calls[1]
    assert kwargs["params"]["path"] == "router"
    assert kwargs["params"]["method"] == "router_set_lan_ip"
    assert kwargs["json"] == {
        "lan_ip": "192.168.1.1",
        "lan_netmask": "255.255.255.0",
    }


def test_set_address_legacy_same_state_without_force_avoids_write():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    client, session = authenticated_client([(address, 200)])

    assert client.lan.set_address_legacy(
        "192.168.1.1",
        "255.255.255.0",
    ) == address

    assert [call[0] for call in session.calls] == ["GET"]



def test_set_static_reservations_rejects_ip_outside_current_lan_before_write():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    client, session = authenticated_client([(address, 200)])

    with pytest.raises(ValueError, match="inside current LAN subnet"):
        client.lan.set_static_reservations(
            [
                {
                    "index": 0,
                    "mac": "02:00:00:00:00:01",
                    "ip": "192.0.2.254",
                }
            ]
        )

    assert len(session.calls) == 1
    assert session.calls[0][0] == "GET"


def test_set_static_reservations_sends_numeric_index_even_if_input_is_string():
    address = {
        "router": {
            "lan_ip": "192.168.1.1",
            "lan_netmask": "255.255.255.0",
        }
    }
    before = {"dhcp": {"cnt": 0, "data": []}}
    after = {
        "dhcp": {
            "cnt": 1,
            "data": [
                {
                    "index": 0,
                    "mac": "02:00:00:00:00:01",
                    "ip": "192.168.1.254",
                }
            ],
        }
    }
    client, session = authenticated_client(
        [
            (address, 200),
            (before, 200),
            ({"responses": [{"data": {"dhcp": {"setting_response": "OK"}}}]}, 200),
            (after, 200),
        ]
    )

    client.lan.set_static_reservations(
        [
            {
                "index": "0",
                "mac": "02:00:00:00:00:01",
                "ip": "192.168.1.254",
            }
        ],
        recovery_attempts=1,
    )

    member = session.calls[2][2]["json"]["requests"][0]
    assert member["data"]["data"][0]["index"] == 0
    assert isinstance(member["data"]["data"][0]["index"], int)


@pytest.mark.parametrize(
    "items",
    [
        [
            {"index": 0, "mac": "02:00:00:00:00:01", "ip": "192.168.1.10"},
            {"index": 1, "mac": "02:00:00:00:00:01", "ip": "192.168.1.11"},
        ],
        [
            {"index": 0, "mac": "02:00:00:00:00:01", "ip": "192.168.1.10"},
            {"index": 1, "mac": "02:00:00:00:00:02", "ip": "192.168.1.10"},
        ],
        [
            {"index": 0, "mac": "01:00:5e:00:00:01", "ip": "192.168.1.10"},
        ],
    ],
)
def test_set_static_reservations_matches_frontend_duplicate_and_multicast_checks(items):
    client, session = authenticated_client([])

    with pytest.raises(ValueError):
        client.lan.set_static_reservations(items)

    assert session.calls == []
