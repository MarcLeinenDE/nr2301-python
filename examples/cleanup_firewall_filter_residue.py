# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


TEST_IP = "203.0.113.77"
TEST_PORT = "65500:65500"


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


def _setting_response(value: object) -> object | None:
    return _find(value, "setting_response")


def _read_all(client: NR2301Client, *, kind: str) -> list[Mapping[str, Any]]:
    if kind == "ip":
        response = client.call(
            "firewall",
            "ww_read_ip_filter",
            data={"ww_ip_filter": {"list": ["all"]}},
        )
    else:
        response = client.call(
            "firewall",
            "ww_read_port_filter",
            data={"ww_port_filter": {"list": ["all"]}},
        )
    value = _find(response, "list")
    if not isinstance(value, list):
        raise RuntimeError(f"{kind} filter all-slot read did not return a list")
    return [item for item in value if isinstance(item, Mapping)]


def _semantic(items: list[Mapping[str, Any]], value_key: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        text = str(item.get(value_key) or "")
        if text not in {"", "0"}:
            result[index] = text
    return result


def _slots(items: list[Mapping[str, Any]], value_key: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {value_key: "0", "index": index} for index in range(10)
    ]
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < 10:
            continue
        value = str(item.get(value_key) or "0")
        result[index] = {value_key: value, "index": index}
    return result


def _cleanup_kind(
    client: NR2301Client,
    *,
    label: str,
    kind: str,
    value_key: str,
    test_value: str,
    mode_method: str,
    disable_field: str,
    switch_method: str,
    outer: str,
    edit_method: str,
) -> None:
    before = _read_all(client, kind=kind)
    semantic_before = _semantic(before, value_key)
    matching = [index for index, value in semantic_before.items() if value == test_value]
    print(f"{label}_ALL_READ_COUNT = {len(before)}")
    print(f"{label}_NONEMPTY_COUNT_BEFORE = {len(semantic_before)}")
    print(f"{label}_SYNTHETIC_MATCH_COUNT = {len(matching)}")

    if not matching:
        print(f"{label}_CLEANUP = NOT_NEEDED")
        return

    original_disable = str(_find(client.call("firewall", mode_method), disable_field))
    if original_disable not in {"0", "1"}:
        raise RuntimeError(f"unexpected {disable_field}={original_disable!r}")

    slots = _slots(before, value_key)
    for index in matching:
        if 0 <= index < len(slots):
            slots[index] = {value_key: "0", "index": index}

    try:
        enable = client.call(
            "firewall",
            switch_method,
            data={outer: {disable_field: "0"}},
        )
        enabled = str(_find(client.call("firewall", mode_method), disable_field)) == "0"
        print(f"{label}_ENABLE_RESPONSE = {_setting_response(enable)!r}")
        print(f"{label}_ENABLED_FOR_CLEANUP = {enabled}")
        if not enabled:
            raise RuntimeError(f"{label} could not be enabled for cleanup")

        write = client.call(
            "firewall",
            edit_method,
            data={outer: {"list": slots}},
        )
        after = _semantic(_read_all(client, kind=kind), value_key)
        cleared = test_value not in after.values()
        print(f"{label}_CLEANUP_WRITE_RESPONSE = {_setting_response(write)!r}")
        print(f"{label}_SYNTHETIC_CLEARED = {cleared}")
        print(f"{label}_NONEMPTY_COUNT_AFTER = {len(after)}")
        if not cleared:
            raise RuntimeError(f"{label} synthetic residue still present")
    finally:
        restore = client.call(
            "firewall",
            switch_method,
            data={outer: {disable_field: original_disable}},
        )
        restored = str(_find(client.call("firewall", mode_method), disable_field)) == original_disable
        print(f"{label}_SWITCH_RESTORE_RESPONSE = {_setting_response(restore)!r}")
        print(f"{label}_SWITCH_RESTORED = {restored}")
        if not restored:
            raise RuntimeError(f"{label} switch restore failed")


def main() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        _cleanup_kind(
            client,
            label="IP_FILTER",
            kind="ip",
            value_key="ip",
            test_value=TEST_IP,
            mode_method="ww_read_switch_mode_state",
            disable_field="ip_filter_disable",
            switch_method="ww_fw_set_disable_info",
            outer="ww_ip_filter",
            edit_method="ww_edit_ip_filter",
        )
        _cleanup_kind(
            client,
            label="PORT_FILTER",
            kind="port",
            value_key="port",
            test_value=TEST_PORT,
            mode_method="ww_read_switch_port_mode_state",
            disable_field="port_filter_disable",
            switch_method="ww_fw_set_port_disable_info",
            outer="ww_port_filter",
            edit_method="ww_edit_port_filter",
        )

    print("FIREWALL_FILTER_RESIDUE_CLEANUP = PASS")


if __name__ == "__main__":
    main()
