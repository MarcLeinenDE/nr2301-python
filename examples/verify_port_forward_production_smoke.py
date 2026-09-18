# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Focused physical smoke for the production Port Forward helper."""

import importlib.util
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nr2301 import NR2301Client

NAME = "SDK-PF-PROD"
MAC = "02:00:00:00:00:01"
PORT = "65512"


def load_firewall(client: NR2301Client) -> Any:
    path = Path(os.environ["NR2301_FIREWALL_PROD_MODULE"]).resolve()
    spec = importlib.util.spec_from_file_location("nr2301_firewall_prod_pf", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load production firewall module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(f"PRODUCTION_FIREWALL_MODULE = {path}")
    return module.FirewallNamespace(client)


def as01(value: object) -> int:
    text = str(value).strip()
    if text not in {"0", "1"}:
        raise RuntimeError(f"unexpected enable value: {value!r}")
    return int(text)


def semantic(items: object) -> dict[int, tuple[str, str, str, str]]:
    result: dict[int, tuple[str, str, str, str]] = {}
    if not isinstance(items, list):
        return result
    for fallback, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        values = (
            str(item.get("name") or ""),
            str(item.get("mac") or ""),
            str(item.get("local_port") or ""),
            str(item.get("wan_port") or ""),
        )
        if 0 <= index < 5 and any(values):
            result[index] = values
    return result


def boot_time(client: NR2301Client) -> int:
    value = client.device.runtime().get("boot_time")
    if not isinstance(value, int):
        raise RuntimeError(f"boot_time is not int: {value!r}")
    return value


def main() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    if not os.environ.get("NR2301_PASSWORD"):
        raise RuntimeError("NR2301_PASSWORD is required")
    if not os.environ.get("NR2301_FIREWALL_PROD_MODULE"):
        raise RuntimeError("NR2301_FIREWALL_PROD_MODULE is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=os.environ["NR2301_PASSWORD"],
        timeout=10.0,
    ) as client:
        client.login()
        fw = load_firewall(client)
        boot_before = boot_time(client)
        print(f"PORT_FORWARD_BOOT_BEFORE = {boot_before}")

        before = fw.port_forward()
        settings = before.get("settings")
        if not isinstance(settings, Mapping):
            raise RuntimeError("get_port_forward returned no settings object")
        original_enable = as01(settings.get("enable"))
        original = semantic(settings.get("items"))
        free = next((i for i in range(5) if i not in original), None)
        if free is None:
            raise RuntimeError("no free Port Forward slot; nothing was changed")

        original_items = [
            {
                "index": index,
                "name": values[0],
                "mac": values[1],
                "local_port": values[2],
                "wan_port": values[3],
            }
            for index, values in sorted(original.items())
        ]
        synthetic = {
            "index": free,
            "name": NAME,
            "mac": MAC,
            "local_port": PORT,
            "wan_port": PORT,
        }

        print(f"PORT_FORWARD_ORIGINAL_ENABLE = {original_enable}")
        print(f"PORT_FORWARD_SYNTHETIC_SLOT = {free}")

        try:
            response = fw.set_port_forward(True, items=[*original_items, synthetic])
            print(f"PORT_FORWARD_WRITE_RESULT = {response.get('result')!r}")

            after = fw.port_forward().get("settings")
            current = semantic(after.get("items") if isinstance(after, Mapping) else None)
            visible = current.get(free) == (NAME, MAC, PORT, PORT)
            print(f"PORT_FORWARD_WRITE_READBACK = {visible}")
            if not visible:
                raise RuntimeError("synthetic Port Forward rule not visible")
        finally:
            restore = fw.set_port_forward(True, items=original_items)
            print(f"PORT_FORWARD_LIST_RESTORE_RESULT = {restore.get('result')!r}")
            if original_enable == 0:
                restore_enable = fw.set_port_forward(False)
                print(f"PORT_FORWARD_ENABLE_RESTORE_RESULT = {restore_enable.get('result')!r}")

        final_settings = fw.port_forward().get("settings")
        if not isinstance(final_settings, Mapping):
            raise RuntimeError("final get_port_forward returned no settings object")
        final_enable = as01(final_settings.get("enable"))
        final_semantic = semantic(final_settings.get("items"))
        restored = final_enable == original_enable and final_semantic == original
        residue = any(values[0] == NAME for values in final_semantic.values())
        boot_after = boot_time(client)

        print(f"PORT_FORWARD_FINAL_ENABLE = {final_enable}")
        print(f"PORT_FORWARD_RESTORED = {restored}")
        print(f"FINAL_SYNTHETIC_FORWARD_PRESENT = {residue}")
        print(f"PORT_FORWARD_BOOT_AFTER = {boot_after}")
        print(f"PORT_FORWARD_REBOOT_DETECTED = {boot_after < boot_before}")

        if not restored or residue or boot_after < boot_before:
            raise RuntimeError("focused Port Forward smoke did not restore cleanly")

        print("PORT_FORWARD_PRODUCTION_SMOKE = PASS")


if __name__ == "__main__":
    main()
