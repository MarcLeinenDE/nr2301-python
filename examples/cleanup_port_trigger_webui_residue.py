# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Remove the synthetic port-trigger residue left by the first WebUI-shape test.

The stock NR2301 WebUI only submits the 10-slot ``items`` array while the
Port Trigger switch is ON.  Therefore restoring a previously disabled state
with only ``{"enable": 0}`` disables the feature but does not clear stored
items.  This focused recovery reproduces the actual two-step WebUI semantics:

1. enable + submit the full 10-slot list with the synthetic slot emptied;
2. restore the enable state that was present when recovery started.

The script refuses to proceed if any non-synthetic populated trigger rule is
present, so it cannot silently erase an unrelated rule.  USB/management mode
is never touched.
"""

import os
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client

TRIGGER_NAME = "SDK-PT-WEBUI"
TRIGGER_PORT = "65500"
TRIGGER_START = "65501"
TRIGGER_END = "65501"
TRIGGER_SIGNATURE = (TRIGGER_NAME, TRIGGER_PORT, TRIGGER_START, TRIGGER_END)


def require_write_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")


def as01(value: object, field: str) -> int:
    text = str(value).strip()
    if text not in {"0", "1"}:
        raise RuntimeError(f"{field} is not 0/1: {value!r}")
    return int(text)


def trigger_items(settings: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = settings.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def trigger_semantic(
    items: list[Mapping[str, Any]],
) -> dict[int, tuple[str, str, str, str]]:
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


def read_state(client: NR2301Client) -> tuple[int, list[Mapping[str, Any]], dict[int, tuple[str, str, str, str]]]:
    response = client.firewall.port_trigger()
    settings = response.get("settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("get_port_trigger returned no settings object")
    enable = as01(settings.get("enable"), "port_trigger.enable")
    items = trigger_items(settings)
    return enable, items, trigger_semantic(items)


def main() -> None:
    require_write_gate()
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
        original_enable, original_items, original_semantic = read_state(client)

        synthetic_slots = [
            index for index, value in original_semantic.items() if value == TRIGGER_SIGNATURE
        ]
        unrelated = {
            index: value
            for index, value in original_semantic.items()
            if value != TRIGGER_SIGNATURE
        }

        print(f"PORT_TRIGGER_RECOVERY_INITIAL_ENABLE = {original_enable}")
        print(f"PORT_TRIGGER_RECOVERY_SYNTHETIC_SLOTS = {synthetic_slots}")
        print(f"PORT_TRIGGER_RECOVERY_UNRELATED_COUNT = {len(unrelated)}")

        if unrelated:
            raise RuntimeError(
                "recovery aborted: non-synthetic populated port-trigger rule present"
            )

        if not synthetic_slots:
            print("PORT_TRIGGER_RECOVERY_NEEDED = False")
            print("PORT_TRIGGER_RECOVERY = PASS")
            return

        slots = webui_trigger_slots(original_items)
        for index in synthetic_slots:
            slots[index] = {
                "index": index,
                "name": "",
                "trigger_port": "",
                "start_port": "",
                "end_port": "",
            }

        # The stock WebUI only transmits items while ON.  Submit the cleared
        # full list first so the stored synthetic item is actually removed.
        clear_response = client.call(
            "firewall",
            "set_port_trigger",
            data={"enable": 1, "items": slots},
        )
        clear_enable, _, clear_semantic = read_state(client)
        cleared = not any(value == TRIGGER_SIGNATURE for value in clear_semantic.values())
        print(f"PORT_TRIGGER_CLEAR_RESULT = {clear_response.get('result')!r}")
        print(f"PORT_TRIGGER_CLEAR_ENABLE = {clear_enable}")
        print(f"PORT_TRIGGER_SYNTHETIC_CLEARED = {cleared}")
        if clear_response.get("result") != 0 or not cleared or clear_semantic:
            raise RuntimeError("synthetic trigger was not cleared by full empty WebUI list")

        if original_enable == 0:
            restore_response = client.call(
                "firewall", "set_port_trigger", data={"enable": 0}
            )
        else:
            restore_response = client.call(
                "firewall",
                "set_port_trigger",
                data={"enable": 1, "items": slots},
            )

        final_enable, _, final_semantic = read_state(client)
        restored = final_enable == original_enable and final_semantic == {}
        print(f"PORT_TRIGGER_ENABLE_RESTORE_RESULT = {restore_response.get('result')!r}")
        print(f"PORT_TRIGGER_FINAL_ENABLE = {final_enable}")
        print(f"PORT_TRIGGER_FINAL_NONEMPTY_COUNT = {len(final_semantic)}")
        print(f"PORT_TRIGGER_RECOVERY_RESTORED = {restored}")
        if not restored:
            raise RuntimeError("port-trigger cleanup did not restore the clean baseline")

    print("PORT_TRIGGER_RECOVERY = PASS")


if __name__ == "__main__":
    main()
