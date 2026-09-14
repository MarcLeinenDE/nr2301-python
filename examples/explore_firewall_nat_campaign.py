# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import ipaddress
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from nr2301 import NR2301Client


TEST_DOMAIN = "sdk-nr2301.invalid"
TEST_IP_FILTER_IP = "203.0.113.77"
TEST_PORT_FILTER = "65500:65500"
TEST_PF_NAME_PREFIX = "SDK-PF-"
TEST_PT_NAME_PREFIX = "SDK-PT-"


def _write_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")


def _find_value(value: object, key: str) -> object | None:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_value(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, key)
            if found is not None:
                return found
    return None


def _find_mapping(value: object, key: str) -> Mapping[str, Any] | None:
    found = _find_value(value, key)
    return found if isinstance(found, Mapping) else None


def _find_list(value: object, key: str) -> list[Any] | None:
    found = _find_value(value, key)
    return list(found) if isinstance(found, list) else None


def _as_int01(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return int(value.strip())
    raise RuntimeError(f"{field} did not expose a 0/1 value")


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _result_text(response: object) -> str:
    if not isinstance(response, Mapping):
        return type(response).__name__
    result = response.get("result")
    if result is not None:
        return f"result={result!r}"
    setting = _find_value(response, "setting_response")
    if setting is not None:
        return f"setting_response={setting!r}"
    return "mapping-no-result"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _phase(name: str, fn: Callable[[], None], failures: list[str]) -> None:
    print(f"PHASE_{name}_START = True")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - physical campaign keeps later phases usable
        failures.append(name)
        print(f"PHASE_{name}_ERROR = {type(exc).__name__}")
    finally:
        print(f"PHASE_{name}_END = True")


def _firewall_nested(response: Mapping[str, Any]) -> Mapping[str, Any]:
    value = response.get("firewall")
    if isinstance(value, Mapping):
        return value
    return response


def _get_state01(client: NR2301Client, method: str, field: str) -> int:
    response = client.call("firewall", method)
    return _as_int01(_find_value(response, field), field=field)


def _write_and_verify_simple(
    client: NR2301Client,
    *,
    getter: str,
    getter_field: str,
    setter: str,
    setter_data: Callable[[str], Mapping[str, Any]],
    label: str,
) -> None:
    original = _get_state01(client, getter, getter_field)
    target = 1 - original
    changed = False
    try:
        response = client.call("firewall", setter, data=dict(setter_data(str(target))))
        print(f"{label}_WRITE = {_result_text(response)}")
        actual = _get_state01(client, getter, getter_field)
        changed = actual == target
        print(f"{label}_READBACK = {changed}")
        if not changed:
            raise RuntimeError(f"{label} target was not visible")
    finally:
        response = client.call("firewall", setter, data=dict(setter_data(str(original))))
        restored = _get_state01(client, getter, getter_field) == original
        print(f"{label}_RESTORE_WRITE = {_result_text(response)}")
        print(f"{label}_RESTORED = {restored}")
        if not restored:
            raise RuntimeError(f"{label} restore failed")


def _vpn_passthrough_phase(client: NR2301Client) -> None:
    before = client.firewall.vpn_passthrough()
    original = {
        key: _as_int01(_find_value(before, key), field=key)
        for key in ("pptp", "l2tp", "ipsec")
    }
    target = dict(original)
    target["pptp"] = 1 - original["pptp"]
    try:
        response = client.call(
            "firewall",
            "fw_set_vpn_passthrough",
            data={key: str(value) for key, value in target.items()},
        )
        print(f"VPN_PASSTHROUGH_WRITE = {_result_text(response)}")
        after = client.firewall.vpn_passthrough()
        match = all(
            _as_int01(_find_value(after, key), field=key) == value
            for key, value in target.items()
        )
        print(f"VPN_PASSTHROUGH_READBACK = {match}")
        if not match:
            raise RuntimeError("VPN passthrough read-back mismatch")
    finally:
        response = client.call(
            "firewall",
            "fw_set_vpn_passthrough",
            data={key: str(value) for key, value in original.items()},
        )
        restored_state = client.firewall.vpn_passthrough()
        restored = all(
            _as_int01(_find_value(restored_state, key), field=key) == value
            for key, value in original.items()
        )
        print(f"VPN_PASSTHROUGH_RESTORE_WRITE = {_result_text(response)}")
        print(f"VPN_PASSTHROUGH_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("VPN passthrough restore failed")


def _safe_dmz_candidate(client: NR2301Client, current: str) -> str | None:
    dhcp = client.lan.dhcp()
    lan_ip = dhcp.get("lan_ip")
    netmask = dhcp.get("lan_netmask")
    start = dhcp.get("start")
    end = dhcp.get("end")
    if not all(isinstance(value, str) for value in (lan_ip, netmask, start, end)):
        return None

    try:
        network = ipaddress.ip_network(f"{lan_ip}/{netmask}", strict=False)
        router_ip = ipaddress.ip_address(lan_ip)
        dhcp_start = ipaddress.ip_address(start)
        dhcp_end = ipaddress.ip_address(end)
    except ValueError:
        return None

    used: set[ipaddress.IPv4Address] = {router_ip}
    try:
        for item in client.statistics.active_clients().get("clients_info", []):
            if not isinstance(item, Mapping):
                continue
            value = item.get("ip")
            if isinstance(value, str):
                try:
                    parsed = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if isinstance(parsed, ipaddress.IPv4Address):
                    used.add(parsed)
    except Exception:  # noqa: BLE001 - candidate selection can proceed without inventory
        pass

    try:
        current_ip = ipaddress.ip_address(current)
        if isinstance(current_ip, ipaddress.IPv4Address):
            used.add(current_ip)
    except ValueError:
        pass

    hosts = list(network.hosts())
    for candidate in reversed(hosts):
        if not isinstance(candidate, ipaddress.IPv4Address):
            continue
        if candidate in used:
            continue
        if dhcp_start <= candidate <= dhcp_end:
            continue
        return str(candidate)
    return None


def _dmz_phase(client: NR2301Client) -> None:
    before = client.firewall.dmz_info()
    original_value = _find_value(before, "dmz_dest_ip")
    if not isinstance(original_value, str):
        raise RuntimeError("DMZ destination read-back missing")

    # First prove the static frontend shape is accepted for current state.
    same = client.call(
        "firewall",
        "fw_edit_dmz_entry",
        data={"dmz_dest_ip": original_value},
    )
    same_readback = _find_value(client.firewall.dmz_info(), "dmz_dest_ip") == original_value
    print(f"DMZ_EDIT_SAME_STATE_WRITE = {_result_text(same)}")
    print(f"DMZ_EDIT_SAME_STATE_READBACK = {same_readback}")
    if not same_readback:
        raise RuntimeError("DMZ same-state edit was not preserved")

    candidate = _safe_dmz_candidate(client, original_value)
    if candidate is None:
        print("DMZ_EDIT_MUTATION = SKIPPED_NO_SAFE_LAN_CANDIDATE")
        return

    try:
        response = client.call(
            "firewall",
            "fw_edit_dmz_entry",
            data={"dmz_dest_ip": candidate},
        )
        match = _find_value(client.firewall.dmz_info(), "dmz_dest_ip") == candidate
        print(f"DMZ_EDIT_WRITE = {_result_text(response)}")
        print(f"DMZ_EDIT_READBACK = {match}")
        if not match:
            raise RuntimeError("DMZ target was not visible")
    finally:
        response = client.call(
            "firewall",
            "fw_edit_dmz_entry",
            data={"dmz_dest_ip": original_value},
        )
        restored = _find_value(client.firewall.dmz_info(), "dmz_dest_ip") == original_value
        print(f"DMZ_EDIT_RESTORE_WRITE = {_result_text(response)}")
        print(f"DMZ_EDIT_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("DMZ destination restore failed")


def _next_slot(items: Sequence[object], *, limit: int) -> int:
    used = {
        index
        for item in items
        if isinstance(item, Mapping) and (index := _as_int(item.get("index"))) is not None
    }
    for index in range(limit):
        if index not in used:
            return index
    return limit - 1


def _replace_index(items: list[Any], index: int, replacement: Mapping[str, Any]) -> list[Any]:
    result: list[Any] = []
    replaced = False
    for item in items:
        if isinstance(item, Mapping) and _as_int(item.get("index")) == index:
            if not replaced:
                result.append(dict(replacement))
                replaced = True
            continue
        result.append(copy.deepcopy(item))
    if not replaced:
        result.append(dict(replacement))
    return result


def _filter_list_phase(
    client: NR2301Client,
    *,
    kind: str,
    getter: Callable[[], Mapping[str, Any]],
    edit_method: str,
    outer_key: str,
    value_key: str,
    value: str,
) -> None:
    before = getter()
    original_list = _find_list(before, "list")
    if original_list is None:
        raise RuntimeError(f"{kind} list read-back missing")
    slot = _next_slot(original_list, limit=10)
    test_item = {value_key: value, "index": slot}
    mutation = _replace_index(original_list, slot, test_item)

    try:
        response = client.call(
            "firewall",
            edit_method,
            data={outer_key: {"list": mutation}},
        )
        after = getter()
        after_list = _find_list(after, "list") or []
        visible = any(
            isinstance(item, Mapping)
            and _as_int(item.get("index")) == slot
            and str(item.get(value_key)) == value
            for item in after_list
        )
        print(f"{kind}_LIST_WRITE = {_result_text(response)}")
        print(f"{kind}_LIST_READBACK = {visible}")
        if not visible:
            raise RuntimeError(f"{kind} synthetic rule was not visible")
    finally:
        response = client.call(
            "firewall",
            edit_method,
            data={outer_key: {"list": original_list}},
        )
        restored = _canonical(_find_list(getter(), "list") or []) == _canonical(original_list)
        print(f"{kind}_LIST_RESTORE_WRITE = {_result_text(response)}")
        print(f"{kind}_LIST_RESTORED = {restored}")
        if not restored:
            raise RuntimeError(f"{kind} list restore failed")


def _normalize_indexed_values(values: object, *, limit: int = 10) -> list[dict[str, Any]]:
    result = [{"value": "", "index": index} for index in range(limit)]
    if not isinstance(values, list):
        return result
    for item in values:
        if not isinstance(item, Mapping):
            continue
        index = _as_int(item.get("index"))
        if index is None or not 0 <= index < limit:
            continue
        raw = item.get("value")
        result[index] = {"value": "" if raw is None else str(raw), "index": index}
    return result


def _url_filter_phase(client: NR2301Client) -> None:
    before = client.firewall.url_filter()
    settings = _find_mapping(before, "settings")
    if settings is None:
        raise RuntimeError("URL filter settings missing")
    original = copy.deepcopy(dict(settings))

    black = _normalize_indexed_values(original.get("black_items"))
    white = _normalize_indexed_values(original.get("white_items"))
    black[0] = {"value": TEST_DOMAIN, "index": 0}
    mutation = {"mode": "blacklist", "black_items": black, "white_items": white}

    try:
        response = client.call("firewall", "set_url_filter", data=mutation)
        after = client.firewall.url_filter()
        after_settings = _find_mapping(after, "settings") or {}
        visible = (
            str(after_settings.get("mode")) == "blacklist"
            and any(
                isinstance(item, Mapping) and item.get("value") == TEST_DOMAIN
                for item in (after_settings.get("black_items") or [])
            )
        )
        print(f"URL_FILTER_WRITE = {_result_text(response)}")
        print(f"URL_FILTER_READBACK = {visible}")
        if not visible:
            raise RuntimeError("URL filter synthetic item was not visible")
    finally:
        response = client.call("firewall", "set_url_filter", data=original)
        restored_settings = _find_mapping(client.firewall.url_filter(), "settings") or {}
        restored = _canonical(restored_settings) == _canonical(original)
        print(f"URL_FILTER_RESTORE_WRITE = {_result_text(response)}")
        print(f"URL_FILTER_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("URL filter restore failed")


def _pf_empty_item(index: int) -> dict[str, Any]:
    return {"index": index, "name": "", "mac": "", "local_port": "", "wan_port": ""}


def _normalize_pf_items(values: object, *, limit: int = 5) -> list[dict[str, Any]]:
    result = [_pf_empty_item(index) for index in range(limit)]
    if not isinstance(values, list):
        return result
    for fallback, item in enumerate(values[:limit]):
        if not isinstance(item, Mapping):
            continue
        index = _as_int(item.get("index"))
        if index is None or not 0 <= index < limit:
            index = fallback
        result[index] = {
            "index": index,
            "name": str(item.get("name") or ""),
            "mac": str(item.get("mac") or ""),
            "local_port": str(item.get("local_port") or ""),
            "wan_port": str(item.get("wan_port") or ""),
        }
    return result


def _port_forward_phase(client: NR2301Client) -> None:
    before = client.firewall.port_forward()
    settings = _find_mapping(before, "settings")
    if settings is None:
        raise RuntimeError("port-forward settings missing")
    original = copy.deepcopy(dict(settings))
    items = _normalize_pf_items(original.get("items"))

    # Prefer a truly empty slot. If all five are populated, reuse slot 4 and restore it.
    slot = next((i for i, item in enumerate(items) if not item["name"] and not item["mac"]), 4)
    suffix = uuid.uuid4().hex[:6]
    test_name = f"{TEST_PF_NAME_PREFIX}{suffix}"
    items[slot] = {
        "index": slot,
        "name": test_name,
        "mac": "02:00:00:00:00:01",
        "local_port": "65431",
        "wan_port": "65431",
    }
    mutation = {"enable": 1, "items": items}

    try:
        response = client.call("firewall", "set_port_forward", data=mutation)
        after = client.firewall.port_forward()
        after_settings = _find_mapping(after, "settings") or {}
        after_items = after_settings.get("items") or []
        visible = any(
            isinstance(item, Mapping)
            and item.get("name") == test_name
            and str(item.get("local_port")) == "65431"
            and str(item.get("wan_port")) == "65431"
            for item in after_items
        )
        print(f"PORT_FORWARD_WRITE = {_result_text(response)}")
        print(f"PORT_FORWARD_READBACK = {visible}")
        if not visible:
            raise RuntimeError("port-forward synthetic rule was not visible")
    finally:
        response = client.call("firewall", "set_port_forward", data=original)
        restored_settings = _find_mapping(client.firewall.port_forward(), "settings") or {}
        restored = _canonical(restored_settings) == _canonical(original)
        print(f"PORT_FORWARD_RESTORE_WRITE = {_result_text(response)}")
        print(f"PORT_FORWARD_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("port-forward restore failed")


def _port_trigger_phase(client: NR2301Client) -> None:
    before = client.firewall.port_trigger()
    settings = _find_mapping(before, "settings")
    if settings is None:
        raise RuntimeError("port-trigger settings missing")
    original = copy.deepcopy(dict(settings))
    keys = sorted(str(key) for key in original.keys())
    raw_items = original.get("items")
    item_keys: list[str] = []
    if isinstance(raw_items, list) and raw_items and isinstance(raw_items[0], Mapping):
        item_keys = sorted(str(key) for key in raw_items[0].keys())
    print(f"PORT_TRIGGER_SETTINGS_KEYS = {','.join(keys)}")
    print(f"PORT_TRIGGER_ITEM_KEYS = {','.join(item_keys) if item_keys else '<none>'}")

    # First test the strongest non-guessing hypothesis: setter mirrors getter settings.
    response = client.call("firewall", "set_port_trigger", data=original)
    same_after = _find_mapping(client.firewall.port_trigger(), "settings") or {}
    same = _canonical(same_after) == _canonical(original)
    print(f"PORT_TRIGGER_SAME_STATE_WRITE = {_result_text(response)}")
    print(f"PORT_TRIGGER_SAME_STATE_READBACK = {same}")
    if not same:
        raise RuntimeError("port-trigger getter-shaped same-state write did not round-trip")

    # If an existing item exposes its schema, mutate only the name/ports using the
    # observed keys. Empty-list firmware remains a separately reported open detail.
    if not (isinstance(raw_items, list) and raw_items and isinstance(raw_items[0], Mapping)):
        print("PORT_TRIGGER_MUTATION = UNRESOLVED_EMPTY_ITEM_SCHEMA")
        return

    first = dict(raw_items[0])
    suffix = uuid.uuid4().hex[:6]
    candidates = {
        "name": f"{TEST_PT_NAME_PREFIX}{suffix}",
        "rule_name": f"{TEST_PT_NAME_PREFIX}{suffix}",
        "out_port": "65432",
        "in_port": "65433",
        "trigger_port": "65432",
        "open_port": "65433",
    }
    changed_fields = []
    for key, value in candidates.items():
        if key in first:
            first[key] = value
            changed_fields.append(key)
    if not changed_fields:
        print("PORT_TRIGGER_MUTATION = UNRESOLVED_UNKNOWN_ITEM_KEYS")
        return

    mutation = copy.deepcopy(original)
    items = list(raw_items)
    items[0] = first
    mutation["items"] = items
    try:
        response = client.call("firewall", "set_port_trigger", data=mutation)
        after_settings = _find_mapping(client.firewall.port_trigger(), "settings") or {}
        after_items = after_settings.get("items") or []
        visible = bool(after_items and isinstance(after_items[0], Mapping)) and all(
            str(after_items[0].get(key)) == str(first.get(key)) for key in changed_fields
        )
        print(f"PORT_TRIGGER_MUTATION_FIELDS = {','.join(changed_fields)}")
        print(f"PORT_TRIGGER_WRITE = {_result_text(response)}")
        print(f"PORT_TRIGGER_READBACK = {visible}")
        if not visible:
            raise RuntimeError("port-trigger observed-schema mutation not visible")
    finally:
        response = client.call("firewall", "set_port_trigger", data=original)
        restored = _canonical(_find_mapping(client.firewall.port_trigger(), "settings") or {}) == _canonical(original)
        print(f"PORT_TRIGGER_RESTORE_WRITE = {_result_text(response)}")
        print(f"PORT_TRIGGER_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("port-trigger restore failed")


def _snapshot_summary(client: NR2301Client) -> None:
    port_forward = _find_mapping(client.firewall.port_forward(), "settings") or {}
    port_trigger = _find_mapping(client.firewall.port_trigger(), "settings") or {}
    url_filter = _find_mapping(client.firewall.url_filter(), "settings") or {}
    ip_items = _find_list(client.firewall.ip_filter(), "list") or []
    port_items = _find_list(client.firewall.port_filter(), "list") or []
    print(f"INITIAL_PORT_FORWARD_ITEM_COUNT = {len(port_forward.get('items') or [])}")
    print(f"INITIAL_PORT_TRIGGER_ITEM_COUNT = {len(port_trigger.get('items') or [])}")
    print(f"INITIAL_URL_BLACK_COUNT = {len(url_filter.get('black_items') or [])}")
    print(f"INITIAL_URL_WHITE_COUNT = {len(url_filter.get('white_items') or [])}")
    print(f"INITIAL_IP_FILTER_ITEM_COUNT = {len(ip_items)}")
    print(f"INITIAL_PORT_FILTER_ITEM_COUNT = {len(port_items)}")


def main() -> None:
    _write_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    failures: list[str] = []
    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        _snapshot_summary(client)

        _phase(
            "ADMIN_FROM_WAN",
            lambda: _write_and_verify_simple(
                client,
                getter="get_admin_from_wan",
                getter_field="admin_from_wan_enable",
                setter="set_admin_from_wan",
                setter_data=lambda value: {"admin_from_wan": value},
                label="ADMIN_FROM_WAN",
            ),
            failures,
        )
        _phase(
            "PING_FROM_WAN",
            lambda: _write_and_verify_simple(
                client,
                getter="get_ping_from_wan",
                getter_field="ping_from_wan_enable",
                setter="set_ping_from_wan",
                setter_data=lambda value: {"ping_from_wan": value},
                label="PING_FROM_WAN",
            ),
            failures,
        )
        _phase("VPN_PASSTHROUGH", lambda: _vpn_passthrough_phase(client), failures)
        _phase(
            "DMZ_DISABLE",
            lambda: _write_and_verify_simple(
                client,
                getter="fw_get_disable_info",
                getter_field="dmz_disable",
                setter="fw_set_disable_info",
                setter_data=lambda value: {"dmz_disable": value},
                label="DMZ_DISABLE",
            ),
            failures,
        )
        _phase("DMZ_EDIT", lambda: _dmz_phase(client), failures)
        _phase(
            "UPNP",
            lambda: _write_and_verify_simple(
                client,
                getter="ww_upnp_open_close_state",
                getter_field="upnp_enable",
                setter="ww_upnp_open_close",
                setter_data=lambda value: {"ww_upnp": {"upnp_enable": value}},
                label="UPNP",
            ),
            failures,
        )
        _phase(
            "IP_FILTER_SWITCH",
            lambda: _write_and_verify_simple(
                client,
                getter="ww_read_switch_mode_state",
                getter_field="ip_filter_disable",
                setter="ww_fw_set_disable_info",
                setter_data=lambda value: {"ww_ip_filter": {"ip_filter_disable": value}},
                label="IP_FILTER_SWITCH",
            ),
            failures,
        )
        _phase(
            "PORT_FILTER_SWITCH",
            lambda: _write_and_verify_simple(
                client,
                getter="ww_read_switch_port_mode_state",
                getter_field="port_filter_disable",
                setter="ww_fw_set_port_disable_info",
                setter_data=lambda value: {"ww_port_filter": {"port_filter_disable": value}},
                label="PORT_FILTER_SWITCH",
            ),
            failures,
        )
        _phase(
            "IP_FILTER_LIST",
            lambda: _filter_list_phase(
                client,
                kind="IP_FILTER",
                getter=client.firewall.ip_filter,
                edit_method="ww_edit_ip_filter",
                outer_key="ww_ip_filter",
                value_key="ip",
                value=TEST_IP_FILTER_IP,
            ),
            failures,
        )
        _phase(
            "PORT_FILTER_LIST",
            lambda: _filter_list_phase(
                client,
                kind="PORT_FILTER",
                getter=client.firewall.port_filter,
                edit_method="ww_edit_port_filter",
                outer_key="ww_port_filter",
                value_key="port",
                value=TEST_PORT_FILTER,
            ),
            failures,
        )
        _phase("URL_FILTER", lambda: _url_filter_phase(client), failures)
        _phase("PORT_FORWARD", lambda: _port_forward_phase(client), failures)
        _phase("PORT_TRIGGER", lambda: _port_trigger_phase(client), failures)

        _snapshot_summary(client)

    print(f"FIREWALL_NAT_FAILURE_COUNT = {len(failures)}")
    print(f"FIREWALL_NAT_FAILURES = {','.join(failures) if failures else '<none>'}")
    print(f"FIREWALL_NAT_CAMPAIGN = {'PASS' if not failures else 'PARTIAL'}")


if __name__ == "__main__":
    main()
