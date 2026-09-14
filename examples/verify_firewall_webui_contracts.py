# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Focused reversible verification of source-confirmed NR2301 Firewall contracts.

This is a physical-lab research harness, not a user-facing SDK example. It uses
only request shapes recovered from the shipped NR2301 WebUI. Every mutating
phase snapshots current state, writes a synthetic/reversible change, reads it
back, restores the original state and verifies restore.

USB/management mode is never touched. DMZ clear/delete is deliberately absent
because the current NR2301 WebUI exposes no such operation.
"""

import os
from collections.abc import Mapping
from typing import Any, Callable

from nr2301 import NR2301Client

TEST_IP = "203.0.113.77"
TEST_PORT = "65500:65500"
TRIGGER_NAME = "SDK-PT-WEBUI"
TRIGGER_PORT = "65500"
TRIGGER_START = "65501"
TRIGGER_END = "65501"


def require_write_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")


def find(value: object, key: str) -> object | None:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = find(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find(child, key)
            if found is not None:
                return found
    return None


def setting_response(value: object) -> object | None:
    return find(value, "setting_response")


def as01(value: object, field: str) -> str:
    text = str(value).strip()
    if text not in {"0", "1"}:
        raise RuntimeError(f"{field} is not 0/1: {value!r}")
    return text


def run_phase(name: str, fn: Callable[[], None], failures: list[str]) -> None:
    print(f"PHASE_{name}_START = True")
    try:
        fn()
        print(f"PHASE_{name}_PASS = True")
    except Exception as exc:  # noqa: BLE001 - continue independent recovery phases
        failures.append(name)
        print(f"PHASE_{name}_ERROR = {type(exc).__name__}: {exc}")
    finally:
        print(f"PHASE_{name}_END = True")


def wan_phase(
    client: NR2301Client,
    *,
    getter: Callable[[], Mapping[str, Any]],
    field: str,
    method: str,
    outer: str,
    label: str,
) -> None:
    original = as01(find(getter(), field), field)
    target = "1" if original == "0" else "0"

    def write(value: str) -> Mapping[str, Any]:
        return client.call(
            "firewall",
            method,
            data={outer: {field: value}},
        )

    same = write(original)
    print(f"{label}_SAME_RESPONSE = {setting_response(same)!r}")
    if setting_response(same) != "OK":
        raise RuntimeError("source-confirmed nested same-state body was rejected")
    if as01(find(getter(), field), field) != original:
        raise RuntimeError("same-state write changed state")

    changed = False
    try:
        response = write(target)
        print(f"{label}_WRITE_RESPONSE = {setting_response(response)!r}")
        changed = as01(find(getter(), field), field) == target
        print(f"{label}_READBACK = {changed}")
        if not changed:
            raise RuntimeError("target value was not visible after write")
    finally:
        restore = write(original)
        restored = as01(find(getter(), field), field) == original
        print(f"{label}_RESTORE_RESPONSE = {setting_response(restore)!r}")
        print(f"{label}_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("WAN setting restore failed")


def full_filter_read(client: NR2301Client, outer: str, method: str) -> Mapping[str, Any]:
    return client.call(
        "firewall",
        method,
        data={outer: {"list": ["all"]}},
    )


def list_items(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = find(response, "list")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def semantic_slots(
    items: list[Mapping[str, Any]], value_key: str
) -> dict[int, str]:
    result: dict[int, str] = {}
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        value = str(item.get(value_key) or "")
        if 0 <= index < 10 and value not in {"", "0"}:
            result[index] = value
    return result


def webui_filter_slots(
    items: list[Mapping[str, Any]], value_key: str
) -> list[dict[str, str]]:
    # WebUI source constructs numeric indices but ajaxHandler's default
    # toStringData=true serializes them as strings on the wire.
    slots = [{value_key: "0", "index": str(i)} for i in range(10)]
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < 10:
            continue
        value = str(item.get(value_key) or "0")
        slots[index] = {value_key: value, "index": str(index)}
    return slots


def filter_phase(
    client: NR2301Client,
    *,
    label: str,
    read_method: str,
    outer: str,
    mode_getter: Callable[[], Mapping[str, Any]],
    disable_field: str,
    switch_method: str,
    edit_method: str,
    value_key: str,
    test_value: str,
) -> None:
    original_disable = as01(find(mode_getter(), disable_field), disable_field)
    original_items = list_items(full_filter_read(client, outer, read_method))
    original_semantic = semantic_slots(original_items, value_key)
    original_slots = webui_filter_slots(original_items, value_key)

    free_slot = next((i for i in range(10) if i not in original_semantic), None)
    if free_slot is None:
        raise RuntimeError("no free rule slot")

    mutated = [dict(item) for item in original_slots]
    mutated[free_slot] = {value_key: test_value, "index": str(free_slot)}

    def switch(value: str) -> Mapping[str, Any]:
        return client.call(
            "firewall",
            switch_method,
            data={outer: {disable_field: value}},
        )

    def edit(slots: list[dict[str, str]]) -> Mapping[str, Any]:
        return client.call(
            "firewall",
            edit_method,
            data={outer: {"list": slots}},
        )

    try:
        enable = switch("0")
        enabled = as01(find(mode_getter(), disable_field), disable_field) == "0"
        print(f"{label}_ENABLE_RESPONSE = {setting_response(enable)!r}")
        print(f"{label}_ENABLED = {enabled}")
        if not enabled:
            raise RuntimeError("filter could not be enabled")

        response = edit(mutated)
        after = semantic_slots(
            list_items(full_filter_read(client, outer, read_method)), value_key
        )
        visible = after.get(free_slot) == test_value
        print(f"{label}_WRITE_RESPONSE = {setting_response(response)!r}")
        print(f"{label}_READBACK = {visible}")
        if not visible:
            raise RuntimeError("synthetic rule was not visible in full-list read")

        restore = edit(original_slots)
        restored_semantic = semantic_slots(
            list_items(full_filter_read(client, outer, read_method)), value_key
        )
        list_restored = restored_semantic == original_semantic
        print(f"{label}_LIST_RESTORE_RESPONSE = {setting_response(restore)!r}")
        print(f"{label}_LIST_RESTORED = {list_restored}")
        if not list_restored:
            raise RuntimeError("filter list restore failed")
    finally:
        switch_restore = switch(original_disable)
        switch_restored = (
            as01(find(mode_getter(), disable_field), disable_field)
            == original_disable
        )
        print(f"{label}_SWITCH_RESTORE_RESPONSE = {setting_response(switch_restore)!r}")
        print(f"{label}_SWITCH_RESTORED = {switch_restored}")
        if not switch_restored:
            raise RuntimeError("filter switch restore failed")


def trigger_items(settings: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = settings.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def webui_trigger_slots(items: list[Mapping[str, Any]]) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = [
        {
            "index": i,
            "name": "",
            "trigger_port": "",
            "start_port": "",
            "end_port": "",
        }
        for i in range(10)
    ]
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < 10:
            continue
        slots[index] = {
            "index": index,
            "name": str(item.get("name") or ""),
            "trigger_port": str(item.get("trigger_port") or ""),
            "start_port": str(item.get("start_port") or ""),
            "end_port": str(item.get("end_port") or ""),
        }
    return slots


def trigger_semantic(items: list[Mapping[str, Any]]) -> dict[int, tuple[str, str, str, str]]:
    result: dict[int, tuple[str, str, str, str]] = {}
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        values = (
            str(item.get("name") or ""),
            str(item.get("trigger_port") or ""),
            str(item.get("start_port") or ""),
            str(item.get("end_port") or ""),
        )
        if 0 <= index < 10 and any(values):
            result[index] = values
    return result


def port_trigger_phase(client: NR2301Client) -> None:
    before = client.firewall.port_trigger()
    settings = before.get("settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("get_port_trigger returned no settings object")

    original_enable = int(as01(settings.get("enable"), "port_trigger.enable"))
    original_items = trigger_items(settings)
    original_semantic = trigger_semantic(original_items)
    original_slots = webui_trigger_slots(original_items)
    free_slot = next((i for i in range(10) if i not in original_semantic), None)
    if free_slot is None:
        raise RuntimeError("no free port-trigger slot")

    mutated = [dict(item) for item in original_slots]
    mutated[free_slot] = {
        "index": free_slot,
        "name": TRIGGER_NAME,
        "trigger_port": TRIGGER_PORT,
        "start_port": TRIGGER_START,
        "end_port": TRIGGER_END,
    }

    try:
        response = client.call(
            "firewall",
            "set_port_trigger",
            data={"enable": 1, "items": mutated},
        )
        after = client.firewall.port_trigger()
        after_settings = after.get("settings")
        if not isinstance(after_settings, Mapping):
            raise RuntimeError("port-trigger readback missing settings")
        visible = trigger_semantic(trigger_items(after_settings)).get(free_slot) == (
            TRIGGER_NAME,
            TRIGGER_PORT,
            TRIGGER_START,
            TRIGGER_END,
        )
        print(f"PORT_TRIGGER_WRITE_RESULT = {response.get('result')!r}")
        print(f"PORT_TRIGGER_READBACK = {visible}")
        if not visible:
            raise RuntimeError("synthetic trigger rule was not visible")
    finally:
        restore_body: dict[str, object]
        if original_enable == 0:
            restore_body = {"enable": 0}
        else:
            restore_body = {"enable": 1, "items": original_slots}
        restore = client.call("firewall", "set_port_trigger", data=restore_body)
        restored_response = client.firewall.port_trigger()
        restored_settings = restored_response.get("settings")
        if not isinstance(restored_settings, Mapping):
            raise RuntimeError("port-trigger restore readback missing settings")
        restored_enable = int(as01(restored_settings.get("enable"), "port_trigger.enable"))
        restored_semantic = trigger_semantic(trigger_items(restored_settings))
        restored = (
            restored_enable == original_enable
            and restored_semantic == original_semantic
        )
        print(f"PORT_TRIGGER_RESTORE_RESULT = {restore.get('result')!r}")
        print(f"PORT_TRIGGER_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("port-trigger restore failed")


def main() -> None:
    require_write_gate()
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

        # Keep WAN admin last. The stock WebUI separately schedules
        # router/restart_web_server after an admin setting change; this harness
        # verifies the setter contract itself and deliberately does not invoke
        # that additional disruptive action.
        run_phase(
            "PING_FROM_WAN_WEBUI_SHAPE",
            lambda: wan_phase(
                client,
                getter=client.firewall.ping_from_wan,
                field="ping_from_wan_enable",
                method="set_ping_from_wan",
                outer="ping_from_wan",
                label="PING_FROM_WAN",
            ),
            failures,
        )
        run_phase(
            "IP_FILTER_WEBUI_SHAPE",
            lambda: filter_phase(
                client,
                label="IP_FILTER",
                read_method="ww_read_ip_filter",
                outer="ww_ip_filter",
                mode_getter=client.firewall.ip_filter_mode_state,
                disable_field="ip_filter_disable",
                switch_method="ww_fw_set_disable_info",
                edit_method="ww_edit_ip_filter",
                value_key="ip",
                test_value=TEST_IP,
            ),
            failures,
        )
        run_phase(
            "PORT_FILTER_WEBUI_SHAPE",
            lambda: filter_phase(
                client,
                label="PORT_FILTER",
                read_method="ww_read_port_filter",
                outer="ww_port_filter",
                mode_getter=client.firewall.port_filter_mode_state,
                disable_field="port_filter_disable",
                switch_method="ww_fw_set_port_disable_info",
                edit_method="ww_edit_port_filter",
                value_key="port",
                test_value=TEST_PORT,
            ),
            failures,
        )
        run_phase(
            "PORT_TRIGGER_WEBUI_SHAPE",
            lambda: port_trigger_phase(client),
            failures,
        )
        run_phase(
            "ADMIN_FROM_WAN_WEBUI_SHAPE",
            lambda: wan_phase(
                client,
                getter=client.firewall.admin_from_wan,
                field="admin_from_wan_enable",
                method="set_admin_from_wan",
                outer="admin_from_wan",
                label="ADMIN_FROM_WAN",
            ),
            failures,
        )

        # Final residue check for the synthetic values without printing any
        # unrelated real rules or local identifiers.
        ip_semantic = semantic_slots(
            list_items(full_filter_read(client, "ww_ip_filter", "ww_read_ip_filter")),
            "ip",
        )
        port_semantic = semantic_slots(
            list_items(full_filter_read(client, "ww_port_filter", "ww_read_port_filter")),
            "port",
        )
        trigger_state = client.firewall.port_trigger().get("settings")
        trigger_left = False
        if isinstance(trigger_state, Mapping):
            trigger_left = any(
                value[0] == TRIGGER_NAME
                for value in trigger_semantic(trigger_items(trigger_state)).values()
            )

        print(f"FINAL_SYNTHETIC_IP_PRESENT = {TEST_IP in ip_semantic.values()}")
        print(f"FINAL_SYNTHETIC_PORT_PRESENT = {TEST_PORT in port_semantic.values()}")
        print(f"FINAL_SYNTHETIC_TRIGGER_PRESENT = {trigger_left}")

    print(f"WEBUI_CONTRACT_FAILURE_COUNT = {len(failures)}")
    print(f"WEBUI_CONTRACT_FAILURES = {','.join(failures) if failures else '<none>'}")
    print(f"WEBUI_CONTRACT_VERIFICATION = {'PASS' if not failures else 'PARTIAL'}")


if __name__ == "__main__":
    main()
