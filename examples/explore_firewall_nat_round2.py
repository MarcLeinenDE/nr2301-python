# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Callable

from nr2301 import NR2301Client


TEST_IP = "203.0.113.77"
TEST_PORT = "65500:65500"


def _write_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")


def _find(value: object, key: str) -> object | None:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find(child, key)
            if found is not None:
                return found
    return None


def _int01(value: object, field: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return int(value.strip())
    raise RuntimeError(f"{field} is not 0/1: {value!r}")


def _setting_response(value: object) -> object | None:
    return _find(value, "setting_response")


def _phase(name: str, fn: Callable[[], None], failures: list[str]) -> None:
    print(f"PHASE_{name}_START = True")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - keep later independent phases usable
        failures.append(name)
        print(f"PHASE_{name}_ERROR = {type(exc).__name__}: {exc}")
    finally:
        print(f"PHASE_{name}_END = True")


def _wan_toggle_phase(
    client: NR2301Client,
    *,
    getter: Callable[[], Mapping[str, Any]],
    field: str,
    setter: str,
    request_key: str,
    label: str,
) -> None:
    original = _int01(_find(getter(), field), field)
    target = 1 - original

    # Round 1 proved string "0"/"1" is rejected. The getter exposes a 0/1
    # state, so round 2 tests the smallest remaining type hypothesis: integer.
    same = client.call("firewall", setter, data={request_key: original})
    same_ok = _setting_response(same) == "OK"
    print(f"{label}_INT_SAME_STATE_RESPONSE = {_setting_response(same)!r}")
    print(f"{label}_INT_SAME_STATE_ACCEPTED = {same_ok}")
    if not same_ok:
        raise RuntimeError("integer same-state candidate rejected")

    changed = False
    try:
        response = client.call("firewall", setter, data={request_key: target})
        print(f"{label}_INT_WRITE_RESPONSE = {_setting_response(response)!r}")
        changed = _int01(_find(getter(), field), field) == target
        print(f"{label}_INT_READBACK = {changed}")
        if not changed:
            raise RuntimeError("integer target was not visible")
    finally:
        response = client.call("firewall", setter, data={request_key: original})
        restored = _int01(_find(getter(), field), field) == original
        print(f"{label}_INT_RESTORE_RESPONSE = {_setting_response(response)!r}")
        print(f"{label}_INT_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("WAN setting restore failed")


def _vpn_phase(client: NR2301Client) -> None:
    before = client.firewall.vpn_passthrough()
    original = {
        key: _int01(before.get(key), key)
        for key in ("pptp", "l2tp", "ipsec")
    }
    target = dict(original)
    target["pptp"] = 1 - original["pptp"]

    # Round 1 stringified values returned result=-3. Getter values are native
    # integers, so test the same complete object with native integer values.
    same = client.call("firewall", "fw_set_vpn_passthrough", data=original)
    print(f"VPN_INT_SAME_STATE_RESULT = {same.get('result')!r}")
    if same.get("result") != 0:
        raise RuntimeError("integer same-state VPN candidate rejected")

    try:
        response = client.call("firewall", "fw_set_vpn_passthrough", data=target)
        print(f"VPN_INT_WRITE_RESULT = {response.get('result')!r}")
        after = client.firewall.vpn_passthrough()
        visible = all(_int01(after.get(k), k) == v for k, v in target.items())
        print(f"VPN_INT_READBACK = {visible}")
        if not visible:
            raise RuntimeError("integer VPN target was not visible")
    finally:
        response = client.call("firewall", "fw_set_vpn_passthrough", data=original)
        restored_state = client.firewall.vpn_passthrough()
        restored = all(_int01(restored_state.get(k), k) == v for k, v in original.items())
        print(f"VPN_INT_RESTORE_RESULT = {response.get('result')!r}")
        print(f"VPN_INT_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("VPN passthrough restore failed")


def _list_items(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = _find(response, "list")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _slots(
    items: list[Mapping[str, Any]], *, value_key: str, empty: str = "0"
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {value_key: empty, "index": index} for index in range(10)
    ]
    for fallback, item in enumerate(items):
        raw_index = item.get("index", fallback)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if not 0 <= index < 10:
            continue
        raw = item.get(value_key)
        text = empty if raw in (None, "") else str(raw)
        result[index] = {value_key: text, "index": index}
    return result


def _semantic_nonempty(items: list[Mapping[str, Any]], value_key: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for fallback, item in enumerate(items):
        raw_index = item.get("index", fallback)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        raw = item.get(value_key)
        text = "" if raw is None else str(raw)
        if text not in {"", "0"}:
            result[index] = text
    return result


def _filter_phase(
    client: NR2301Client,
    *,
    label: str,
    getter: Callable[[], Mapping[str, Any]],
    mode_getter: Callable[[], Mapping[str, Any]],
    disable_field: str,
    switch_method: str,
    switch_outer: str,
    edit_method: str,
    edit_outer: str,
    value_key: str,
    test_value: str,
) -> None:
    original_disable = str(_find(mode_getter(), disable_field))
    if original_disable not in {"0", "1"}:
        raise RuntimeError(f"unexpected {disable_field}={original_disable!r}")

    original_items = _list_items(getter())
    original_semantic = _semantic_nonempty(original_items, value_key)
    original_slots = _slots(original_items, value_key=value_key)
    free_slot = next(
        (index for index in range(10) if index not in original_semantic),
        None,
    )
    if free_slot is None:
        raise RuntimeError("no free filter slot for synthetic test")

    mutation = [dict(item) for item in original_slots]
    mutation[free_slot] = {value_key: test_value, "index": free_slot}

    # Related same-generation client code only writes the rule list while the
    # filter is enabled, and serializes empty slots as literal "0".
    try:
        enable = client.call(
            "firewall",
            switch_method,
            data={switch_outer: {disable_field: "0"}},
        )
        enabled = str(_find(mode_getter(), disable_field)) == "0"
        print(f"{label}_ENABLE_RESPONSE = {_setting_response(enable)!r}")
        print(f"{label}_ENABLED = {enabled}")
        if not enabled:
            raise RuntimeError("filter could not be enabled")

        response = client.call(
            "firewall",
            edit_method,
            data={edit_outer: {"list": mutation}},
        )
        after_items = _list_items(getter())
        after_semantic = _semantic_nonempty(after_items, value_key)
        visible = after_semantic.get(free_slot) == test_value
        print(f"{label}_LIST_WRITE_RESPONSE = {_setting_response(response)!r}")
        print(f"{label}_LIST_READBACK = {visible}")
        if not visible:
            raise RuntimeError("synthetic filter rule was not visible")

        restore = client.call(
            "firewall",
            edit_method,
            data={edit_outer: {"list": original_slots}},
        )
        restored_semantic = _semantic_nonempty(_list_items(getter()), value_key)
        list_restored = restored_semantic == original_semantic
        print(f"{label}_LIST_RESTORE_RESPONSE = {_setting_response(restore)!r}")
        print(f"{label}_LIST_RESTORED = {list_restored}")
        if not list_restored:
            raise RuntimeError("filter list restore failed")
    finally:
        switch_restore = client.call(
            "firewall",
            switch_method,
            data={switch_outer: {disable_field: original_disable}},
        )
        switch_restored = str(_find(mode_getter(), disable_field)) == original_disable
        print(f"{label}_SWITCH_RESTORE_RESPONSE = {_setting_response(switch_restore)!r}")
        print(f"{label}_SWITCH_RESTORED = {switch_restored}")
        if not switch_restored:
            raise RuntimeError("filter switch restore failed")


def _preflight(client: NR2301Client) -> None:
    dmz_disable = str(_find(client.firewall.disable_info(), "dmz_disable"))
    url = client.firewall.url_filter()
    settings = url.get("settings", {})
    black = settings.get("black_items", []) if isinstance(settings, Mapping) else []
    white = settings.get("white_items", []) if isinstance(settings, Mapping) else []

    def count_nonempty(values: object) -> int:
        if not isinstance(values, list):
            return 0
        return sum(
            1
            for item in values
            if isinstance(item, Mapping)
            and str(item.get("value") or "") not in {"", "0"}
        )

    print(f"PREFLIGHT_DMZ_DISABLE = {dmz_disable!r}")
    print(f"PREFLIGHT_URL_MODE = {settings.get('mode')!r}")
    print(f"PREFLIGHT_URL_BLACK_NONEMPTY = {count_nonempty(black)}")
    print(f"PREFLIGHT_URL_WHITE_NONEMPTY = {count_nonempty(white)}")
    if dmz_disable != "1":
        raise RuntimeError("DMZ quarantine requires dmz_disable='1'")
    if count_nonempty(black) or count_nonempty(white):
        raise RuntimeError("URL filter is not clean before round 2")


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
        _preflight(client)

        _phase(
            "ADMIN_FROM_WAN_INT",
            lambda: _wan_toggle_phase(
                client,
                getter=client.firewall.admin_from_wan,
                field="admin_from_wan_enable",
                setter="set_admin_from_wan",
                request_key="admin_from_wan",
                label="ADMIN_FROM_WAN",
            ),
            failures,
        )
        _phase(
            "PING_FROM_WAN_INT",
            lambda: _wan_toggle_phase(
                client,
                getter=client.firewall.ping_from_wan,
                field="ping_from_wan_enable",
                setter="set_ping_from_wan",
                request_key="ping_from_wan",
                label="PING_FROM_WAN",
            ),
            failures,
        )
        _phase("VPN_PASSTHROUGH_INT", lambda: _vpn_phase(client), failures)
        _phase(
            "IP_FILTER_LIST_SENTINEL",
            lambda: _filter_phase(
                client,
                label="IP_FILTER",
                getter=client.firewall.ip_filter,
                mode_getter=client.firewall.ip_filter_mode_state,
                disable_field="ip_filter_disable",
                switch_method="ww_fw_set_disable_info",
                switch_outer="ww_ip_filter",
                edit_method="ww_edit_ip_filter",
                edit_outer="ww_ip_filter",
                value_key="ip",
                test_value=TEST_IP,
            ),
            failures,
        )
        _phase(
            "PORT_FILTER_LIST_SENTINEL",
            lambda: _filter_phase(
                client,
                label="PORT_FILTER",
                getter=client.firewall.port_filter,
                mode_getter=client.firewall.port_filter_mode_state,
                disable_field="port_filter_disable",
                switch_method="ww_fw_set_port_disable_info",
                switch_outer="ww_port_filter",
                edit_method="ww_edit_port_filter",
                edit_outer="ww_port_filter",
                value_key="port",
                test_value=TEST_PORT,
            ),
            failures,
        )

        trigger = client.firewall.port_trigger()
        settings = trigger.get("settings", {})
        print(f"PORT_TRIGGER_ENABLE = {settings.get('enable')!r}")
        print(f"PORT_TRIGGER_ITEM_COUNT = {len(settings.get('items') or [])}")
        print("PORT_TRIGGER_ITEM_SCHEMA = QUARANTINED_FOR_WEBUI_CRAWL")

        _preflight(client)

    print(f"FIREWALL_NAT_ROUND2_FAILURE_COUNT = {len(failures)}")
    print(f"FIREWALL_NAT_ROUND2_FAILURES = {','.join(failures) if failures else '<none>'}")
    print(f"FIREWALL_NAT_ROUND2 = {'PASS' if not failures else 'PARTIAL'}")


if __name__ == "__main__":
    main()
