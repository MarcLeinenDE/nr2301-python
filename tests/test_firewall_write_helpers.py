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


def assert_single_post(session, api_method, body):
    assert len(session.calls) == 1
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "firewall"
    assert kwargs["params"]["method"] == api_method
    assert kwargs["json"] == body


@pytest.mark.parametrize(
    ("helper", "enabled", "api_method", "body"),
    [
        (
            "set_ping_from_wan",
            True,
            "set_ping_from_wan",
            {"ping_from_wan": {"ping_from_wan_enable": "1"}},
        ),
        (
            "set_ping_from_wan",
            False,
            "set_ping_from_wan",
            {"ping_from_wan": {"ping_from_wan_enable": "0"}},
        ),
        (
            "set_admin_from_wan",
            True,
            "set_admin_from_wan",
            {"admin_from_wan": {"admin_from_wan_enable": "1"}},
        ),
        (
            "set_upnp_enabled",
            False,
            "ww_upnp_open_close",
            {"ww_upnp": {"upnp_enable": "0"}},
        ),
        (
            "set_dmz_enabled",
            True,
            "fw_set_disable_info",
            {"dmz_disable": "0"},
        ),
        (
            "set_ip_filter_enabled",
            True,
            "ww_fw_set_disable_info",
            {"ww_ip_filter": {"ip_filter_disable": "0"}},
        ),
        (
            "set_port_filter_enabled",
            False,
            "ww_fw_set_port_disable_info",
            {"ww_port_filter": {"port_filter_disable": "1"}},
        ),
    ],
)
def test_boolean_firewall_write_helpers_use_verified_wire_shapes(
    helper, enabled, api_method, body
):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    assert getattr(client.firewall, helper)(enabled) == payload
    assert_single_post(session, api_method, body)


def test_admin_from_wan_helper_does_not_hide_web_server_restart():
    client, session = authenticated_client({"firewall": {"setting_response": "OK"}})

    client.firewall.set_admin_from_wan(True)

    assert len(session.calls) == 1
    assert session.calls[0][2]["params"]["method"] == "set_admin_from_wan"


def test_vpn_passthrough_uses_native_json_integers():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.firewall.set_vpn_passthrough(
        pptp=True, l2tp=False, ipsec=True
    ) == payload

    assert_single_post(
        session,
        "fw_set_vpn_passthrough",
        {"pptp": 1, "l2tp": 0, "ipsec": 1},
    )


def test_dmz_destination_write_rejects_unverified_clear():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="clear/delete"):
        client.firewall.set_dmz_destination("")

    assert session.calls == []


def test_dmz_destination_write_uses_verified_edit_method():
    payload = {"firewall": {"setting_response": "OK"}}
    client, session = authenticated_client(payload)

    assert client.firewall.set_dmz_destination("192.0.2.10") == payload
    assert_single_post(
        session,
        "fw_edit_dmz_entry",
        {"dmz_dest_ip": "192.0.2.10"},
    )


def test_replace_ip_filter_rules_builds_ten_string_index_slots():
    payload = {"firewall": {"setting_response": "OK"}}
    client, session = authenticated_client(payload)

    assert client.firewall.replace_ip_filter_rules(
        ["203.0.113.77", None, "203.0.113.88"]
    ) == payload

    slots = [
        {"ip": "203.0.113.77", "index": "0"},
        {"ip": "0", "index": "1"},
        {"ip": "203.0.113.88", "index": "2"},
        *[{"ip": "0", "index": str(i)} for i in range(3, 10)],
    ]
    assert_single_post(
        session,
        "ww_edit_ip_filter",
        {"ww_ip_filter": {"list": slots}},
    )


def test_replace_port_filter_rules_builds_ten_string_index_slots():
    payload = {"firewall": {"setting_response": "OK"}}
    client, session = authenticated_client(payload)

    assert client.firewall.replace_port_filter_rules(["65500:65500"]) == payload

    slots = [
        {"port": "65500:65500", "index": "0"},
        *[{"port": "0", "index": str(i)} for i in range(1, 10)],
    ]
    assert_single_post(
        session,
        "ww_edit_port_filter",
        {"ww_port_filter": {"list": slots}},
    )


@pytest.mark.parametrize(
    "helper",
    ["replace_ip_filter_rules", "replace_port_filter_rules"],
)
def test_filter_rule_helpers_reject_more_than_ten_slots(helper):
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="at most 10"):
        getattr(client.firewall, helper)(["1"] * 11)

    assert session.calls == []


def test_port_trigger_enabled_write_uses_native_indices_and_ten_slots():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    item = {
        "index": 2,
        "name": "example",
        "trigger_port": "4000",
        "start_port": "5000",
        "end_port": "5001",
    }
    assert client.firewall.set_port_trigger(True, items=[item]) == payload

    expected_items = [
        {
            "index": i,
            "name": "",
            "trigger_port": "",
            "start_port": "",
            "end_port": "",
        }
        for i in range(10)
    ]
    expected_items[2] = item
    assert_single_post(
        session,
        "set_port_trigger",
        {"enable": 1, "items": expected_items},
    )


def test_port_trigger_disable_does_not_send_items_or_imply_delete():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.firewall.set_port_trigger(False) == payload
    assert_single_post(session, "set_port_trigger", {"enable": 0})


def test_port_trigger_rejects_items_with_disabled_form():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="cannot be supplied"):
        client.firewall.set_port_trigger(False, items=[{"index": 0}])

    assert session.calls == []


def test_port_trigger_rejects_duplicate_or_out_of_range_indices():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="duplicate"):
        client.firewall.set_port_trigger(
            True,
            items=[{"index": 0}, {"index": 0}],
        )

    with pytest.raises(ValueError, match="between 0 and 9"):
        client.firewall.set_port_trigger(True, items=[{"index": 10}])

    assert session.calls == []


def test_port_forward_enabled_write_uses_native_indices_and_five_slots():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    item = {
        "index": 1,
        "name": "example",
        "mac": "02:00:00:00:00:01",
        "local_port": "65500",
        "wan_port": "65500",
    }
    assert client.firewall.set_port_forward(True, items=[item]) == payload

    expected_items = [
        {
            "index": i,
            "name": "",
            "mac": "",
            "local_port": "",
            "wan_port": "",
        }
        for i in range(5)
    ]
    expected_items[1] = item
    assert_single_post(
        session,
        "set_port_forward",
        {"enable": 1, "items": expected_items},
    )


def test_port_forward_rejects_more_than_five_slots_or_out_of_range_index():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="at most 5"):
        client.firewall.set_port_forward(
            True,
            items=[{"index": i} for i in range(6)],
        )

    with pytest.raises(ValueError, match="between 0 and 4"):
        client.firewall.set_port_forward(True, items=[{"index": 5}])

    assert session.calls == []


def test_port_forward_disabled_form_is_enable_only():
    payload = {"result": 1}
    client, session = authenticated_client(payload)

    assert client.firewall.set_port_forward(False) == payload
    assert_single_post(session, "set_port_forward", {"enable": 0})


def test_url_filter_blacklist_uses_native_indices_and_ten_slots():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.firewall.set_url_filter(
        "blacklist", items=["example.invalid", None]
    ) == payload

    items = [
        {"value": "example.invalid", "index": 0},
        {"value": "", "index": 1},
        *[{"value": "", "index": i} for i in range(2, 10)],
    ]
    assert_single_post(
        session,
        "set_url_filter",
        {"mode": "blacklist", "black_items": items},
    )


def test_url_filter_disable_is_mode_only_and_rejects_items():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.firewall.set_url_filter("disable") == payload
    assert_single_post(session, "set_url_filter", {"mode": "disable"})

    client, session = authenticated_client()
    with pytest.raises(ValueError, match="disabled"):
        client.firewall.set_url_filter("disable", items=["example.invalid"])
    assert session.calls == []
