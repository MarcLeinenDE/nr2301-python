# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any

import pytest

from nr2301 import NR2301Client, NR2301Error


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical Firewall/NAT write tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration

_PF_FIELDS = ("name", "mac", "local_port", "wan_port")
_PT_FIELDS = ("name", "trigger_port", "start_port", "end_port")
_SYNTHETIC_IPS = ("203.0.113.77", "203.0.113.78", "203.0.113.79")
_SYNTHETIC_PORTS = ("65500:65500", "65499:65499", "65498:65498")
_SYNTHETIC_URLS = (
    "sdk-firewall-test.invalid",
    "sdk-firewall-test-2.invalid",
    "sdk-firewall-test-3.invalid",
)
_SYNTHETIC_MACS = (
    "02:00:00:00:00:FA",
    "02:00:00:00:00:F9",
    "02:00:00:00:00:F8",
)


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        yield client


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        pytest.fail(f"{label} did not return an object")
    return value


def _firewall(response: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    return _mapping(response.get("firewall"), f"{label}.firewall")


def _binary(value: Any, label: str) -> int:
    if isinstance(value, bool):
        pytest.fail(f"{label} returned a boolean instead of 0/1")
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        pytest.fail(f"{label} did not return 0/1")
    if numeric not in {0, 1}:
        pytest.fail(f"{label} returned unsupported value {numeric!r}")
    return numeric


def _flag(response: Mapping[str, Any], key: str, label: str) -> int:
    return _binary(_firewall(response, label).get(key), f"{label}.{key}")


def _vpn_state(router, *, timeout: float = 10.0) -> tuple[int, int, int]:
    response = router.firewall.vpn_passthrough(timeout=timeout)
    return (
        _binary(response.get("pptp"), "vpn.pptp"),
        _binary(response.get("l2tp"), "vpn.l2tp"),
        _binary(response.get("ipsec"), "vpn.ipsec"),
    )


def _indexed_state(
    response: Mapping[str, Any],
    *,
    fields: tuple[str, ...],
    limit: int,
    label: str,
) -> tuple[int, tuple[tuple[str, ...], ...]]:
    settings = _mapping(response.get("settings"), f"{label}.settings")
    enable = _binary(settings.get("enable"), f"{label}.settings.enable")
    raw_items = settings.get("items")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        pytest.fail(f"{label}.settings.items did not return a list")

    slots = [tuple("" for _ in fields) for _ in range(limit)]
    seen: set[int] = set()
    for raw in raw_items:
        item = _mapping(raw, f"{label}.item")
        index_value = item.get("index")
        if isinstance(index_value, bool):
            pytest.fail(f"{label} returned invalid boolean index")
        try:
            index = int(index_value)
        except (TypeError, ValueError):
            pytest.fail(f"{label} returned invalid index")
        if not 0 <= index < limit:
            pytest.fail(f"{label} returned out-of-range index {index}")
        if index in seen:
            pytest.fail(f"{label} returned duplicate index {index}")
        seen.add(index)
        slots[index] = tuple(str(item.get(field) or "") for field in fields)

    return enable, tuple(slots)



def _normalize_indexed_slots(
    slots: tuple[tuple[str, ...], ...],
    fields: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    normalized: list[tuple[str, ...]] = []
    for values in slots:
        row = []
        for field, value in zip(fields, values):
            row.append(value.lower() if field == "mac" else value)
        normalized.append(tuple(row))
    return tuple(normalized)

def _items_from_slots(
    slots: tuple[tuple[str, ...], ...],
    fields: tuple[str, ...],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for index, values in enumerate(slots):
        if not any(values):
            continue
        items.append(
            {"index": index, **{field: value for field, value in zip(fields, values)}}
        )
    return items


def _rule_state(
    response: Mapping[str, Any],
    *,
    value_key: str,
    label: str,
) -> tuple[str, ...]:
    raw_list = _firewall(response, label).get("list")
    if not isinstance(raw_list, list):
        pytest.fail(f"{label}.firewall.list did not return a list")

    slots = ["0"] * 10
    seen: set[int] = set()
    for raw in raw_list:
        item = _mapping(raw, f"{label}.item")
        index_value = item.get("index")
        if isinstance(index_value, bool):
            pytest.fail(f"{label} returned invalid boolean index")
        try:
            index = int(index_value)
        except (TypeError, ValueError):
            pytest.fail(f"{label} returned invalid index")
        if not 0 <= index < 10:
            pytest.fail(f"{label} returned out-of-range index {index}")
        if index in seen:
            pytest.fail(f"{label} returned duplicate index {index}")
        seen.add(index)
        value = item.get(value_key)
        slots[index] = "0" if value in {None, "", "0"} else str(value)
    return tuple(slots)


def _url_values(raw_items: Any, label: str) -> tuple[str, ...]:
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        pytest.fail(f"{label} did not return a list")

    slots = [""] * 10
    seen: set[int] = set()
    for raw in raw_items:
        item = _mapping(raw, f"{label}.item")
        index_value = item.get("index")
        if isinstance(index_value, bool):
            pytest.fail(f"{label} returned invalid boolean index")
        try:
            index = int(index_value)
        except (TypeError, ValueError):
            pytest.fail(f"{label} returned invalid index")
        if not 0 <= index < 10:
            pytest.fail(f"{label} returned out-of-range index {index}")
        if index in seen:
            pytest.fail(f"{label} returned duplicate index {index}")
        seen.add(index)
        slots[index] = str(item.get("value") or "")
    return tuple(slots)


def _url_state(
    router,
    *,
    timeout: float = 10.0,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    response = router.firewall.url_filter(timeout=timeout)
    settings = _mapping(response.get("settings"), "url_filter.settings")
    mode = settings.get("mode")
    if mode not in {"disable", "blacklist", "whitelist"}:
        pytest.fail(f"url_filter returned unsupported mode {mode!r}")
    return (
        str(mode),
        _url_values(settings.get("black_items"), "url_filter.black_items"),
        _url_values(settings.get("white_items"), "url_filter.white_items"),
    )


def _url_state_with_recovery(
    router,
    *,
    attempts: int = 5,
    timeout: float = 10.0,
    delay: float = 1.0,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    last_error: NR2301Error | None = None
    for attempt in range(1, attempts + 1):
        try:
            state = _url_state(router, timeout=timeout)
            if attempt > 1:
                print(
                    "FIREWALL_URL_FILTER_READBACK_RECOVERED"
                    f" attempt={attempt}"
                    f" previous_error={type(last_error).__name__ if last_error else None}",
                    flush=True,
                )
            return state
        except NR2301Error as exc:
            last_error = exc
            print(
                "FIREWALL_URL_FILTER_READBACK_RETRY"
                f" attempt={attempt}"
                f" error={type(exc).__name__}",
                flush=True,
            )
            try:
                router.login()
            except NR2301Error:
                pass
            if attempt < attempts and delay:
                time.sleep(delay)

    assert last_error is not None
    raise last_error


def _dmz_destination(router, *, timeout: float = 10.0) -> str:
    response = router.firewall.dmz_info(timeout=timeout)
    value = _firewall(response, "dmz_info").get("dmz_dest_ip")
    if not isinstance(value, str):
        pytest.fail("dmz_info did not return string dmz_dest_ip")
    return value


def _snapshot(router, *, timeout: float = 10.0) -> dict[str, object]:
    return {
        "dmz_enabled": 1
        - _flag(router.firewall.disable_info(timeout=timeout), "dmz_disable", "dmz"),
        "dmz_destination": _dmz_destination(router, timeout=timeout),
        "vpn": _vpn_state(router, timeout=timeout),
        "admin_from_wan": _flag(
            router.firewall.admin_from_wan(timeout=timeout),
            "admin_from_wan_enable",
            "admin_from_wan",
        ),
        "ping_from_wan": _flag(
            router.firewall.ping_from_wan(timeout=timeout),
            "ping_from_wan_enable",
            "ping_from_wan",
        ),
        "port_forward": _indexed_state(
            router.firewall.port_forward(timeout=timeout),
            fields=_PF_FIELDS,
            limit=5,
            label="port_forward",
        ),
        "port_trigger": _indexed_state(
            router.firewall.port_trigger(timeout=timeout),
            fields=_PT_FIELDS,
            limit=10,
            label="port_trigger",
        ),
        "url_filter": _url_state(router, timeout=timeout),
        "ip_filter_rules": _rule_state(
            router.firewall.ip_filter(timeout=timeout),
            value_key="ip",
            label="ip_filter",
        ),
        "ip_filter_enabled": 1
        - _flag(
            router.firewall.ip_filter_mode_state(timeout=timeout),
            "ip_filter_disable",
            "ip_filter_mode",
        ),
        "port_filter_rules": _rule_state(
            router.firewall.port_filter(timeout=timeout),
            value_key="port",
            label="port_filter",
        ),
        "port_filter_enabled": 1
        - _flag(
            router.firewall.port_filter_mode_state(timeout=timeout),
            "port_filter_disable",
            "port_filter_mode",
        ),
        "upnp_enabled": _flag(
            router.firewall.upnp_state(timeout=timeout),
            "upnp_enable",
            "upnp",
        ),
    }



def _snapshot_with_recovery(
    router,
    *,
    attempts: int = 6,
    timeout: float = 10.0,
    delay: float = 1.0,
) -> dict[str, object]:
    last_error: NR2301Error | None = None
    for attempt in range(1, attempts + 1):
        try:
            snapshot = _snapshot(router, timeout=timeout)
            if attempt > 1:
                print(
                    "FIREWALL_SNAPSHOT_RECOVERED"
                    f" attempt={attempt}"
                    f" previous_error={type(last_error).__name__ if last_error else None}",
                    flush=True,
                )
            return snapshot
        except NR2301Error as exc:
            last_error = exc
            print(
                "FIREWALL_SNAPSHOT_RETRY"
                f" attempt={attempt}"
                f" error={type(exc).__name__}",
                flush=True,
            )
            try:
                router.login()
            except NR2301Error:
                pass
            if attempt < attempts and delay:
                time.sleep(delay)

    assert last_error is not None
    raise last_error

def _choose_unique(candidates: tuple[str, ...], existing: set[str]) -> str:
    for candidate in candidates:
        if candidate not in existing:
            return candidate
    pytest.fail("all reserved synthetic candidates are already present")


def _mutate_slot_values(
    original: tuple[str, ...],
    *,
    candidates: tuple[str, ...],
) -> tuple[str, ...]:
    values = list(original)
    target = next((i for i, value in enumerate(values) if value in {"", "0"}), len(values) - 1)
    synthetic = _choose_unique(candidates, {value for value in values if value not in {"", "0"}})
    values[target] = synthetic
    return tuple(values)


def _mutate_indexed_slots(
    original: tuple[tuple[str, ...], ...],
    *,
    fields: tuple[str, ...],
    kind: str,
) -> tuple[tuple[str, ...], ...]:
    slots = list(original)
    target = next((i for i, values in enumerate(slots) if not any(values)), len(slots) - 1)

    if kind == "port_forward":
        existing_macs = {values[1] for values in slots if len(values) > 1 and values[1]}
        mac = _choose_unique(_SYNTHETIC_MACS, existing_macs)
        replacement = ("SDK-PF-PHYSICAL", mac, "65500", "65500")
    elif kind == "port_trigger":
        replacement = ("SDK-PT-PHYSICAL", "65500", "65501", "65501")
    else:
        raise AssertionError(f"unknown indexed mutation kind: {kind}")

    if len(replacement) != len(fields):
        raise AssertionError("synthetic indexed rule shape mismatch")
    slots[target] = replacement
    return tuple(slots)


def _restore(router, original: Mapping[str, object]) -> None:
    # Restore full stored lists before their enable switches.
    ip_rules = tuple(original["ip_filter_rules"])
    router.firewall.replace_ip_filter_rules(list(ip_rules), timeout=10.0)
    router.firewall.set_ip_filter_enabled(bool(original["ip_filter_enabled"]), timeout=10.0)

    port_rules = tuple(original["port_filter_rules"])
    router.firewall.replace_port_filter_rules(list(port_rules), timeout=10.0)
    router.firewall.set_port_filter_enabled(
        bool(original["port_filter_enabled"]), timeout=10.0
    )

    pf_enable, pf_slots = original["port_forward"]
    pf_items = _items_from_slots(pf_slots, _PF_FIELDS)
    if pf_enable or pf_items:
        router.firewall.set_port_forward(True, items=pf_items, timeout=10.0)
    if not pf_enable:
        router.firewall.set_port_forward(False, timeout=10.0)

    pt_enable, pt_slots = original["port_trigger"]
    pt_items = _items_from_slots(pt_slots, _PT_FIELDS)
    if pt_enable or pt_items:
        router.firewall.set_port_trigger(True, items=pt_items, timeout=10.0)
    if not pt_enable:
        router.firewall.set_port_trigger(False, timeout=10.0)

    url_mode, black_items, white_items = original["url_filter"]
    if url_mode == "blacklist":
        router.firewall.set_url_filter("blacklist", items=list(black_items), timeout=10.0)
    elif url_mode == "whitelist":
        router.firewall.set_url_filter("whitelist", items=list(white_items), timeout=10.0)
    else:
        # The physical test mutates only the blacklist when starting disabled,
        # so restore that stored list before returning to disabled mode.
        router.firewall.set_url_filter("blacklist", items=list(black_items), timeout=10.0)
        router.firewall.set_url_filter("disable", timeout=10.0)

    pptp, l2tp, ipsec = original["vpn"]
    router.firewall.set_vpn_passthrough(
        pptp=bool(pptp), l2tp=bool(l2tp), ipsec=bool(ipsec), timeout=10.0
    )
    router.firewall.set_admin_from_wan(bool(original["admin_from_wan"]), timeout=10.0)
    router.firewall.set_ping_from_wan(bool(original["ping_from_wan"]), timeout=10.0)
    router.firewall.set_upnp_enabled(bool(original["upnp_enabled"]), timeout=10.0)
    router.firewall.set_dmz_enabled(bool(original["dmz_enabled"]), timeout=10.0)


def test_firewall_write_lifecycle_and_exact_restore(router):
    original = _snapshot_with_recovery(router)

    try:
        router.firewall.set_dmz_enabled(not bool(original["dmz_enabled"]), timeout=10.0)
        assert _snapshot_with_recovery(router)["dmz_enabled"] == 1 - int(original["dmz_enabled"])
        print("FIREWALL_DMZ_ENABLE_WRITE changed=True readback=True", flush=True)

        pptp, l2tp, ipsec = original["vpn"]
        expected_vpn = (1 - pptp, l2tp, ipsec)
        router.firewall.set_vpn_passthrough(
            pptp=bool(expected_vpn[0]),
            l2tp=bool(expected_vpn[1]),
            ipsec=bool(expected_vpn[2]),
            timeout=10.0,
        )
        assert _vpn_state(router) == expected_vpn
        print("FIREWALL_VPN_PASSTHROUGH_WRITE changed=True readback=True", flush=True)

        router.firewall.set_admin_from_wan(
            not bool(original["admin_from_wan"]), timeout=10.0
        )
        assert (
            _flag(
                router.firewall.admin_from_wan(timeout=10.0),
                "admin_from_wan_enable",
                "admin_from_wan",
            )
            == 1 - int(original["admin_from_wan"])
        )
        print("FIREWALL_ADMIN_FROM_WAN_WRITE changed=True readback=True", flush=True)

        router.firewall.set_ping_from_wan(
            not bool(original["ping_from_wan"]), timeout=10.0
        )
        assert (
            _flag(
                router.firewall.ping_from_wan(timeout=10.0),
                "ping_from_wan_enable",
                "ping_from_wan",
            )
            == 1 - int(original["ping_from_wan"])
        )
        print("FIREWALL_PING_FROM_WAN_WRITE changed=True readback=True", flush=True)

        mutated_ip = _mutate_slot_values(
            tuple(original["ip_filter_rules"]), candidates=_SYNTHETIC_IPS
        )
        router.firewall.replace_ip_filter_rules(list(mutated_ip), timeout=10.0)
        assert (
            _rule_state(
                router.firewall.ip_filter(timeout=10.0),
                value_key="ip",
                label="ip_filter",
            )
            == mutated_ip
        )
        print("FIREWALL_IP_FILTER_RULE_WRITE changed=True readback=True", flush=True)

        router.firewall.set_ip_filter_enabled(
            not bool(original["ip_filter_enabled"]), timeout=10.0
        )
        assert (
            1
            - _flag(
                router.firewall.ip_filter_mode_state(timeout=10.0),
                "ip_filter_disable",
                "ip_filter_mode",
            )
            == 1 - int(original["ip_filter_enabled"])
        )
        print("FIREWALL_IP_FILTER_MODE_WRITE changed=True readback=True", flush=True)

        mutated_port = _mutate_slot_values(
            tuple(original["port_filter_rules"]), candidates=_SYNTHETIC_PORTS
        )
        router.firewall.replace_port_filter_rules(list(mutated_port), timeout=10.0)
        assert (
            _rule_state(
                router.firewall.port_filter(timeout=10.0),
                value_key="port",
                label="port_filter",
            )
            == mutated_port
        )
        print("FIREWALL_PORT_FILTER_RULE_WRITE changed=True readback=True", flush=True)

        router.firewall.set_port_filter_enabled(
            not bool(original["port_filter_enabled"]), timeout=10.0
        )
        assert (
            1
            - _flag(
                router.firewall.port_filter_mode_state(timeout=10.0),
                "port_filter_disable",
                "port_filter_mode",
            )
            == 1 - int(original["port_filter_enabled"])
        )
        print("FIREWALL_PORT_FILTER_MODE_WRITE changed=True readback=True", flush=True)

        pf_enable, pf_slots = original["port_forward"]
        mutated_pf = _mutate_indexed_slots(
            pf_slots, fields=_PF_FIELDS, kind="port_forward"
        )
        router.firewall.set_port_forward(
            True, items=_items_from_slots(mutated_pf, _PF_FIELDS), timeout=10.0
        )
        assert _indexed_state(
            router.firewall.port_forward(timeout=10.0),
            fields=_PF_FIELDS,
            limit=5,
            label="port_forward",
        ) == (1, _normalize_indexed_slots(mutated_pf, _PF_FIELDS))
        print("FIREWALL_PORT_FORWARD_WRITE changed=True readback=True", flush=True)

        pt_enable, pt_slots = original["port_trigger"]
        mutated_pt = _mutate_indexed_slots(
            pt_slots, fields=_PT_FIELDS, kind="port_trigger"
        )
        router.firewall.set_port_trigger(
            True, items=_items_from_slots(mutated_pt, _PT_FIELDS), timeout=10.0
        )
        assert _indexed_state(
            router.firewall.port_trigger(timeout=10.0),
            fields=_PT_FIELDS,
            limit=10,
            label="port_trigger",
        ) == (1, mutated_pt)
        print("FIREWALL_PORT_TRIGGER_WRITE changed=True readback=True", flush=True)

        url_mode, black_items, white_items = original["url_filter"]
        if url_mode == "whitelist":
            mutated_urls = _mutate_slot_values(
                tuple(white_items), candidates=_SYNTHETIC_URLS
            )
            router.firewall.set_url_filter(
                "whitelist", items=list(mutated_urls), timeout=10.0
            )
            assert _url_state_with_recovery(router)[0:1] == ("whitelist",)
            assert _url_state_with_recovery(router)[2] == mutated_urls
        else:
            mutated_urls = _mutate_slot_values(
                tuple(black_items), candidates=_SYNTHETIC_URLS
            )
            router.firewall.set_url_filter(
                "blacklist", items=list(mutated_urls), timeout=10.0
            )
            assert _url_state_with_recovery(router)[0:2] == ("blacklist", mutated_urls)
        print("FIREWALL_URL_FILTER_WRITE changed=True readback=True", flush=True)

        router.firewall.set_upnp_enabled(
            not bool(original["upnp_enabled"]), timeout=10.0
        )
        assert (
            _flag(
                router.firewall.upnp_state(timeout=10.0),
                "upnp_enable",
                "upnp",
            )
            == 1 - int(original["upnp_enabled"])
        )
        print("FIREWALL_UPNP_WRITE changed=True readback=True", flush=True)

    finally:
        _restore(router, original)

    final = _snapshot_with_recovery(router)
    assert final == original
    print(
        "FIREWALL_FINAL"
        " dmz_restored=True"
        " vpn_restored=True"
        " wan_controls_restored=True"
        " filters_restored=True"
        " nat_rules_restored=True"
        " upnp_restored=True",
        flush=True,
    )
