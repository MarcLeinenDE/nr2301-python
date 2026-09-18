# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Physical smoke for the production FirewallNamespace from PR #24.

The script may load the exact production firewall.py through
NR2301_FIREWALL_PROD_MODULE, so it can be run from an older local checkout
without replacing local source files.

It never calls router_call_reboot, restart_web_server, factory reset, or any
USB/management-mode mutation. DMZ destination clear/delete is not attempted.
"""

import importlib.util
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from nr2301 import NR2301Client

TEST_IP = "203.0.113.88"
TEST_PORT = "65510:65510"
TRIGGER_NAME = "SDK-PT-PROD"
TRIGGER_PORT = "65510"
TRIGGER_START = "65511"
TRIGGER_END = "65511"
FORWARD_NAME = "SDK-PF-PROD"
FORWARD_MAC = "02-00-00-00-00-01"
FORWARD_PORT = "65512"
URL_VALUE = "nr2301-prod-smoke.invalid"


def require_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    if not os.environ.get("NR2301_PASSWORD"):
        raise RuntimeError("NR2301_PASSWORD is required")


def production_firewall(client: NR2301Client) -> Any:
    override = os.environ.get("NR2301_FIREWALL_PROD_MODULE")
    if not override:
        return client.firewall
    path = Path(override).resolve()
    spec = importlib.util.spec_from_file_location("nr2301_firewall_prod_smoke", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load production firewall module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(f"PRODUCTION_FIREWALL_MODULE = {path}")
    return module.FirewallNamespace(client)


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


def as01(value: object, name: str) -> int:
    text = str(value).strip()
    if text not in {"0", "1"}:
        raise RuntimeError(f"{name} is not 0/1: {value!r}")
    return int(text)


def boot_time(client: NR2301Client) -> int:
    value = client.device.runtime().get("boot_time")
    if not isinstance(value, int):
        raise RuntimeError(f"router/get_runtime_info boot_time is not int: {value!r}")
    return value


def list_items(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = find(response, "list")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def filter_values(items: list[Mapping[str, Any]], key: str) -> list[str | None]:
    values: list[str | None] = [None] * 10
    for fallback, item in enumerate(items):
        try:
            index = int(item.get("index", fallback))
        except (TypeError, ValueError):
            continue
        if 0 <= index < 10:
            text = str(item.get(key) or "")
            values[index] = None if text in {"", "0"} else text
    return values


def indexed_semantic(
    items: object, fields: tuple[str, ...]
) -> dict[int, tuple[str, ...]]:
    result: dict[int, tuple[str, ...]] = {}
    if not isinstance(items, list):
        return result
    for fallback, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            continue
        try:
            index = int(raw.get("index", fallback))
        except (TypeError, ValueError):
            continue
        values = tuple(str(raw.get(field) or "") for field in fields)
        if 0 <= index < 10 and any(values):
            result[index] = values
    return result


def url_values(items: object) -> list[str | None]:
    values: list[str | None] = [None] * 10
    if not isinstance(items, list):
        return values
    for fallback, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            continue
        try:
            index = int(raw.get("index", fallback))
        except (TypeError, ValueError):
            continue
        if 0 <= index < 10:
            text = str(raw.get("value") or "")
            values[index] = text or None
    return values


def phase(
    name: str,
    client: NR2301Client,
    fn: Callable[[], None],
    failures: list[str],
) -> None:
    print(f"PHASE_{name}_START = True")
    before = boot_time(client)
    print(f"PHASE_{name}_BOOT_BEFORE = {before}")
    try:
        fn()
        after = boot_time(client)
        print(f"PHASE_{name}_BOOT_AFTER = {after}")
        rebooted = after < before
        print(f"PHASE_{name}_REBOOT_DETECTED = {rebooted}")
        if rebooted:
            raise RuntimeError("router boot_time reset during phase")
        print(f"PHASE_{name}_PASS = True")
    except Exception as exc:  # noqa: BLE001
        failures.append(name)
        print(f"PHASE_{name}_ERROR = {type(exc).__name__}: {exc}")
    finally:
        print(f"PHASE_{name}_END = True")


def simple_same_state(fw: Any) -> None:
    dmz_enabled = as01(find(fw.disable_info(), "dmz_disable"), "dmz_disable") == 0
    fw.set_dmz_enabled(dmz_enabled)
    if (as01(find(fw.disable_info(), "dmz_disable"), "dmz_disable") == 0) != dmz_enabled:
        raise RuntimeError("DMZ enable same-state readback mismatch")
    print("SIMPLE_DMZ_ENABLE_SAME_STATE = True")

    destination = find(fw.dmz_info(), "dmz_dest_ip")
    if isinstance(destination, str) and destination.strip():
        fw.set_dmz_destination(destination)
        if find(fw.dmz_info(), "dmz_dest_ip") != destination:
            raise RuntimeError("DMZ destination same-state readback mismatch")
        print("SIMPLE_DMZ_DESTINATION_SAME_STATE = True")
    else:
        print("SIMPLE_DMZ_DESTINATION_SAME_STATE = SKIPPED_EMPTY")

    vpn = fw.vpn_passthrough()
    expected_vpn = {
        key: int(vpn.get(key, 0))
        for key in ("pptp", "l2tp", "ipsec")
    }
    if any(value not in {0, 1} for value in expected_vpn.values()):
        raise RuntimeError(f"unexpected VPN passthrough state: {expected_vpn}")
    fw.set_vpn_passthrough(
        pptp=bool(expected_vpn["pptp"]),
        l2tp=bool(expected_vpn["l2tp"]),
        ipsec=bool(expected_vpn["ipsec"]),
    )
    after_vpn = fw.vpn_passthrough()
    if any(int(after_vpn.get(k, -1)) != v for k, v in expected_vpn.items()):
        raise RuntimeError("VPN passthrough same-state readback mismatch")
    print("SIMPLE_VPN_SAME_STATE = True")

    ping = as01(find(fw.ping_from_wan(), "ping_from_wan_enable"), "ping_from_wan_enable")
    fw.set_ping_from_wan(bool(ping))
    if as01(find(fw.ping_from_wan(), "ping_from_wan_enable"), "ping_from_wan_enable") != ping:
        raise RuntimeError("WAN ping same-state readback mismatch")
    print("SIMPLE_WAN_PING_SAME_STATE = True")

    admin = as01(find(fw.admin_from_wan(), "admin_from_wan_enable"), "admin_from_wan_enable")
    fw.set_admin_from_wan(bool(admin))
    if as01(find(fw.admin_from_wan(), "admin_from_wan_enable"), "admin_from_wan_enable") != admin:
        raise RuntimeError("WAN admin same-state readback mismatch")
    print("SIMPLE_WAN_ADMIN_SAME_STATE = True")

    upnp = as01(find(fw.upnp_state(), "upnp_enable"), "upnp_enable")
    fw.set_upnp_enabled(bool(upnp))
    if as01(find(fw.upnp_state(), "upnp_enable"), "upnp_enable") != upnp:
        raise RuntimeError("UPnP same-state readback mismatch")
    print("SIMPLE_UPNP_SAME_STATE = True")


def filter_lifecycle(
    fw: Any,
    *,
    label: str,
    getter: Callable[[], Mapping[str, Any]],
    mode_getter: Callable[[], Mapping[str, Any]],
    enabled_setter: Callable[[bool], Mapping[str, Any]],
    replace: Callable[[list[str | None]], Mapping[str, Any]],
    disable_field: str,
    value_key: str,
    test_value: str,
) -> None:
    original_enabled = as01(find(mode_getter(), disable_field), disable_field) == 0
    original = filter_values(list_items(getter()), value_key)
    free = next((i for i, value in enumerate(original) if value is None), None)
    if free is None:
        raise RuntimeError(f"{label}: no free slot")

    mutated = list(original)
    mutated[free] = test_value
    try:
        enabled_setter(True)
        replace(mutated)
        readback = filter_values(list_items(getter()), value_key)
        visible = readback[free] == test_value
        print(f"{label}_SYNTHETIC_SLOT = {free}")
        print(f"{label}_WRITE_READBACK = {visible}")
        if not visible:
            raise RuntimeError(f"{label}: synthetic rule not visible")

        replace(original)
        restored = filter_values(list_items(getter()), value_key) == original
        print(f"{label}_LIST_RESTORED = {restored}")
        if not restored:
            raise RuntimeError(f"{label}: list restore failed")
    finally:
        enabled_setter(original_enabled)

    enabled_restored = (
        as01(find(mode_getter(), disable_field), disable_field) == 0
    ) == original_enabled
    print(f"{label}_ENABLE_RESTORED = {enabled_restored}")
    if not enabled_restored:
        raise RuntimeError(f"{label}: enable restore failed")


def port_trigger_lifecycle(fw: Any) -> None:
    before = fw.port_trigger()
    settings = before.get("settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("port trigger getter missing settings")
    original_enable = as01(settings.get("enable"), "port_trigger.enable")
    fields = ("name", "trigger_port", "start_port", "end_port")
    original = indexed_semantic(settings.get("items"), fields)
    free = next((i for i in range(10) if i not in original), None)
    if free is None:
        raise RuntimeError("port trigger: no free slot")

    original_items = [
        {
            "index": index,
            "name": values[0],
            "trigger_port": values[1],
            "start_port": values[2],
            "end_port": values[3],
        }
        for index, values in sorted(original.items())
    ]
    synthetic = {
        "index": free,
        "name": TRIGGER_NAME,
        "trigger_port": TRIGGER_PORT,
        "start_port": TRIGGER_START,
        "end_port": TRIGGER_END,
    }

    try:
        fw.set_port_trigger(True, items=[*original_items, synthetic])
        now = fw.port_trigger().get("settings")
        current = indexed_semantic(now.get("items") if isinstance(now, Mapping) else None, fields)
        visible = current.get(free) == (
            TRIGGER_NAME,
            TRIGGER_PORT,
            TRIGGER_START,
            TRIGGER_END,
        )
        print(f"PORT_TRIGGER_SYNTHETIC_SLOT = {free}")
        print(f"PORT_TRIGGER_WRITE_READBACK = {visible}")
        if not visible:
            raise RuntimeError("port trigger synthetic rule not visible")
    finally:
        fw.set_port_trigger(True, items=original_items)
        if original_enable == 0:
            fw.set_port_trigger(False)

    final_settings = fw.port_trigger().get("settings")
    if not isinstance(final_settings, Mapping):
        raise RuntimeError("port trigger final getter missing settings")
    restored = (
        as01(final_settings.get("enable"), "port_trigger.enable") == original_enable
        and indexed_semantic(final_settings.get("items"), fields) == original
    )
    print(f"PORT_TRIGGER_RESTORED = {restored}")
    if not restored:
        raise RuntimeError("port trigger restore failed")


def port_forward_lifecycle(fw: Any) -> None:
    before = fw.port_forward()
    settings = before.get("settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("port forward getter missing settings")
    original_enable = as01(settings.get("enable"), "port_forward.enable")
    fields = ("name", "mac", "local_port", "wan_port")
    original = indexed_semantic(settings.get("items"), fields)
    free = next((i for i in range(10) if i not in original), None)
    if free is None:
        raise RuntimeError("port forward: no free slot")

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
        "name": FORWARD_NAME,
        "mac": FORWARD_MAC,
        "local_port": FORWARD_PORT,
        "wan_port": FORWARD_PORT,
    }

    try:
        fw.set_port_forward(True, items=[*original_items, synthetic])
        now = fw.port_forward().get("settings")
        current = indexed_semantic(now.get("items") if isinstance(now, Mapping) else None, fields)
        visible = current.get(free) == (
            FORWARD_NAME,
            FORWARD_MAC,
            FORWARD_PORT,
            FORWARD_PORT,
        )
        print(f"PORT_FORWARD_SYNTHETIC_SLOT = {free}")
        print(f"PORT_FORWARD_WRITE_READBACK = {visible}")
        if not visible:
            raise RuntimeError("port forward synthetic rule not visible")
    finally:
        fw.set_port_forward(True, items=original_items)
        if original_enable == 0:
            fw.set_port_forward(False)

    final_settings = fw.port_forward().get("settings")
    if not isinstance(final_settings, Mapping):
        raise RuntimeError("port forward final getter missing settings")
    restored = (
        as01(final_settings.get("enable"), "port_forward.enable") == original_enable
        and indexed_semantic(final_settings.get("items"), fields) == original
    )
    print(f"PORT_FORWARD_RESTORED = {restored}")
    if not restored:
        raise RuntimeError("port forward restore failed")


def url_filter_lifecycle(fw: Any) -> None:
    before = fw.url_filter()
    settings = before.get("settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("URL filter getter missing settings")
    original_mode = str(settings.get("mode") or "disable")
    if original_mode not in {"disable", "blacklist", "whitelist"}:
        raise RuntimeError(f"unexpected URL filter mode: {original_mode!r}")
    original_black = url_values(settings.get("black_items"))
    original_white = url_values(settings.get("white_items"))
    free = next((i for i, value in enumerate(original_black) if value is None), None)
    if free is None:
        raise RuntimeError("URL filter: no free blacklist slot")
    mutated = list(original_black)
    mutated[free] = URL_VALUE

    try:
        fw.set_url_filter("blacklist", items=mutated)
        now = fw.url_filter().get("settings")
        black_now = url_values(now.get("black_items") if isinstance(now, Mapping) else None)
        visible = black_now[free] == URL_VALUE
        print(f"URL_FILTER_SYNTHETIC_SLOT = {free}")
        print(f"URL_FILTER_WRITE_READBACK = {visible}")
        if not visible:
            raise RuntimeError("URL filter synthetic rule not visible")
    finally:
        # Remove the synthetic value before restoring the original active mode.
        fw.set_url_filter("blacklist", items=original_black)
        if original_mode == "whitelist":
            fw.set_url_filter("whitelist", items=original_white)
        elif original_mode == "disable":
            fw.set_url_filter("disable")

    final = fw.url_filter().get("settings")
    if not isinstance(final, Mapping):
        raise RuntimeError("URL filter final getter missing settings")
    final_mode = str(final.get("mode") or "disable")
    synthetic_left = URL_VALUE in {
        value for value in url_values(final.get("black_items")) if value is not None
    }
    restored = final_mode == original_mode and not synthetic_left
    print(f"URL_FILTER_RESTORED = {restored}")
    if not restored:
        raise RuntimeError("URL filter restore failed")


def main() -> None:
    require_gate()
    failures: list[str] = []

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=os.environ["NR2301_PASSWORD"],
        timeout=10.0,
    ) as client:
        client.login()
        fw = production_firewall(client)
        initial_boot = boot_time(client)
        print(f"PRODUCTION_SMOKE_INITIAL_BOOT_TIME = {initial_boot}")

        phase("SIMPLE_SAME_STATE", client, lambda: simple_same_state(fw), failures)
        phase(
            "IP_FILTER_LIFECYCLE",
            client,
            lambda: filter_lifecycle(
                fw,
                label="IP_FILTER",
                getter=fw.ip_filter,
                mode_getter=fw.ip_filter_mode_state,
                enabled_setter=fw.set_ip_filter_enabled,
                replace=fw.replace_ip_filter_rules,
                disable_field="ip_filter_disable",
                value_key="ip",
                test_value=TEST_IP,
            ),
            failures,
        )
        phase(
            "PORT_FILTER_LIFECYCLE",
            client,
            lambda: filter_lifecycle(
                fw,
                label="PORT_FILTER",
                getter=fw.port_filter,
                mode_getter=fw.port_filter_mode_state,
                enabled_setter=fw.set_port_filter_enabled,
                replace=fw.replace_port_filter_rules,
                disable_field="port_filter_disable",
                value_key="port",
                test_value=TEST_PORT,
            ),
            failures,
        )
        phase(
            "PORT_TRIGGER_LIFECYCLE",
            client,
            lambda: port_trigger_lifecycle(fw),
            failures,
        )
        phase(
            "PORT_FORWARD_LIFECYCLE",
            client,
            lambda: port_forward_lifecycle(fw),
            failures,
        )
        phase(
            "URL_FILTER_LIFECYCLE",
            client,
            lambda: url_filter_lifecycle(fw),
            failures,
        )

        final_boot = boot_time(client)
        print(f"PRODUCTION_SMOKE_FINAL_BOOT_TIME = {final_boot}")
        print(f"PRODUCTION_SMOKE_REBOOT_DETECTED = {final_boot < initial_boot}")

        # Final sanitized residue checks.
        ip_values = filter_values(list_items(fw.ip_filter()), "ip")
        port_values = filter_values(list_items(fw.port_filter()), "port")
        pt_settings = fw.port_trigger().get("settings")
        pf_settings = fw.port_forward().get("settings")
        url_settings = fw.url_filter().get("settings")

        trigger_left = False
        if isinstance(pt_settings, Mapping):
            trigger_left = any(
                values[0] == TRIGGER_NAME
                for values in indexed_semantic(
                    pt_settings.get("items"),
                    ("name", "trigger_port", "start_port", "end_port"),
                ).values()
            )
        forward_left = False
        if isinstance(pf_settings, Mapping):
            forward_left = any(
                values[0] == FORWARD_NAME
                for values in indexed_semantic(
                    pf_settings.get("items"),
                    ("name", "mac", "local_port", "wan_port"),
                ).values()
            )
        url_left = False
        if isinstance(url_settings, Mapping):
            url_left = URL_VALUE in {
                value
                for value in url_values(url_settings.get("black_items"))
                if value is not None
            }

        print(f"FINAL_SYNTHETIC_IP_PRESENT = {TEST_IP in ip_values}")
        print(f"FINAL_SYNTHETIC_PORT_PRESENT = {TEST_PORT in port_values}")
        print(f"FINAL_SYNTHETIC_TRIGGER_PRESENT = {trigger_left}")
        print(f"FINAL_SYNTHETIC_FORWARD_PRESENT = {forward_left}")
        print(f"FINAL_SYNTHETIC_URL_PRESENT = {url_left}")

    print(f"PRODUCTION_SMOKE_FAILURE_COUNT = {len(failures)}")
    print(f"PRODUCTION_SMOKE_FAILURES = {','.join(failures) if failures else '<none>'}")
    print(f"PRODUCTION_FIREWALL_SMOKE = {'PASS' if not failures else 'PARTIAL'}")


if __name__ == "__main__":
    main()
