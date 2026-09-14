# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Mapping
from typing import Any, Callable

from nr2301 import NR2301Client


TEST_DDNS_DOMAIN = "sdk-nr2301.invalid"
TEST_VPN_SERVER = "192.0.2.1"
TEST_VPN_USER = "sdk-probe"
TEST_VPN_PASSWORD = "sdk-probe"
TEST_VPN_PREFIX = "SDK-VPN-"


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


def _result(value: object) -> int | None:
    raw = _find(value, "result")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _phase(name: str, fn: Callable[[], None], failures: list[str]) -> None:
    print(f"PHASE_{name}_START = True")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - keep later independent phases usable
        failures.append(name)
        # Never print exception text: it can contain sensitive response material.
        print(f"PHASE_{name}_ERROR_TYPE = {type(exc).__name__}")
    finally:
        print(f"PHASE_{name}_END = True")


def _subset(value: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    missing = [key for key in keys if key not in value]
    if missing:
        raise RuntimeError("required getter fields are missing")
    return {key: copy.deepcopy(value[key]) for key in keys}


def _wan_phase(client: NR2301Client) -> None:
    keys = (
        "wan_type_primary",
        "static",
        "wifi_extender",
        "mobile_ping_enable",
        "ping_address",
    )
    before_raw = client.call("cm", "get_wan_settings")
    before = _subset(before_raw, keys)

    print(f"WAN_PRIMARY_PRESENT = {bool(before.get('wan_type_primary'))}")
    print(f"WAN_STATIC_OBJECT_PRESENT = {isinstance(before.get('static'), Mapping)}")
    print(f"WAN_EXTENDER_OBJECT_PRESENT = {isinstance(before.get('wifi_extender'), Mapping)}")
    print(f"WAN_EXTENDER_CREDENTIAL_FIELDS_PRESENT = {isinstance(before.get('wifi_extender'), Mapping) and 'ssid' in before['wifi_extender'] and 'password' in before['wifi_extender']}")

    same = client.call("cm", "set_wan_settings", data=copy.deepcopy(before))
    same_result = _result(same)
    same_after = _subset(client.call("cm", "get_wan_settings"), keys)
    same_readback = same_after == before
    print(f"WAN_SAME_STATE_RESULT = {same_result!r}")
    print(f"WAN_SAME_STATE_READBACK = {same_readback}")
    if same_result != 0 or not same_readback:
        raise RuntimeError("WAN getter-shaped same-state write failed")

    raw_ping = before.get("mobile_ping_enable")
    if isinstance(raw_ping, bool) or not isinstance(raw_ping, int) or raw_ping not in (0, 1):
        print("WAN_MOBILE_PING_MUTATION = SKIPPED_UNEXPECTED_TYPE")
        return

    mutation = copy.deepcopy(before)
    mutation["mobile_ping_enable"] = 1 - raw_ping
    try:
        response = client.call("cm", "set_wan_settings", data=mutation)
        after = _subset(client.call("cm", "get_wan_settings"), keys)
        target_visible = after.get("mobile_ping_enable") == mutation["mobile_ping_enable"]
        other_unchanged = all(
            after.get(key) == before.get(key)
            for key in keys
            if key != "mobile_ping_enable"
        )
        print(f"WAN_MOBILE_PING_WRITE_RESULT = {_result(response)!r}")
        print(f"WAN_MOBILE_PING_READBACK = {target_visible}")
        print(f"WAN_OTHER_FIELDS_UNCHANGED = {other_unchanged}")
        if _result(response) != 0 or not target_visible or not other_unchanged:
            raise RuntimeError("WAN mobile-ping mutation failed")
    finally:
        restore = client.call("cm", "set_wan_settings", data=copy.deepcopy(before))
        restored = _subset(client.call("cm", "get_wan_settings"), keys) == before
        print(f"WAN_RESTORE_RESULT = {_result(restore)!r}")
        print(f"WAN_RESTORED = {restored}")
        if _result(restore) != 0 or not restored:
            raise RuntimeError("WAN restore failed")


def _ddns_phase(client: NR2301Client) -> None:
    before = client.call("ddns", "get_ddns")
    enabled = str(before.get("enabled", ""))
    service = str(before.get("service_name", ""))
    domain = str(before.get("domain", ""))
    username = str(before.get("username", ""))
    password = str(before.get("password", ""))

    # Never print credential/provider contents. Only classification booleans.
    print(f"DDNS_ENABLED = {enabled == '1'}")
    print(f"DDNS_SERVICE_PRESENT = {bool(service)}")
    print(f"DDNS_DOMAIN_PRESENT = {bool(domain)}")
    print(f"DDNS_USERNAME_PRESENT = {bool(username)}")
    print(f"DDNS_PASSWORD_PRESENT = {bool(password)}")

    safe = (
        enabled == "0"
        and service == "no-ip.com"
        and not domain
        and not username
        and not password
    )
    if not safe:
        print("DDNS_WRITE_SAFETY = SKIPPED_PRESERVED_OR_TOKEN_UNKNOWN_PROFILE")
        return

    original = {
        "enabled": enabled,
        "service_name": service,
        "domain": domain,
        "username": username,
        "password": password,
    }
    same = client.call("ddns", "set_ddns", data=copy.deepcopy(original))
    same_after = client.call("ddns", "get_ddns")
    same_readback = all(str(same_after.get(k, "")) == str(v) for k, v in original.items())
    print(f"DDNS_SAME_STATE_RESULT = {_result(same)!r}")
    print(f"DDNS_SAME_STATE_READBACK = {same_readback}")
    if _result(same) != 0 or not same_readback:
        raise RuntimeError("DDNS same-state write failed")

    mutation = dict(original)
    mutation["domain"] = TEST_DDNS_DOMAIN
    try:
        response = client.call("ddns", "set_ddns", data=mutation)
        after = client.call("ddns", "get_ddns")
        visible = str(after.get("domain", "")) == TEST_DDNS_DOMAIN
        still_disabled = str(after.get("enabled", "")) == "0"
        print(f"DDNS_DISABLED_DOMAIN_WRITE_RESULT = {_result(response)!r}")
        print(f"DDNS_DISABLED_DOMAIN_READBACK = {visible}")
        print(f"DDNS_REMAINED_DISABLED = {still_disabled}")
        if _result(response) != 0 or not visible or not still_disabled:
            raise RuntimeError("DDNS disabled-profile mutation failed")
    finally:
        restore = client.call("ddns", "set_ddns", data=copy.deepcopy(original))
        restored = client.call("ddns", "get_ddns")
        restored_ok = all(str(restored.get(k, "")) == str(v) for k, v in original.items())
        print(f"DDNS_RESTORE_RESULT = {_result(restore)!r}")
        print(f"DDNS_RESTORED = {restored_ok}")
        if _result(restore) != 0 or not restored_ok:
            raise RuntimeError("DDNS restore failed")


def _tr069_phase(client: NR2301Client) -> None:
    # WW_OPERATOR_ZYXEL frontend payload: getter fields below, excluding the
    # non-platform periodic_notify_* and custom_notify_json fields that were
    # previously proven to cause result=-1001.
    keys = (
        "enable",
        "acs_url",
        "acs_username",
        "acs_password",
        "periodic_inform_enable",
        "periodic_inform_interval",
        "req_authtype",
        "req_username",
        "req_password",
    )
    before_raw = client.call("tr069", "get_config")
    before = _subset(before_raw, keys)

    print(f"TR069_ENABLED = {before.get('enable') == 1}")
    print(f"TR069_ACS_CONFIG_PRESENT = {bool(before.get('acs_url'))}")
    print(f"TR069_ACS_CREDENTIALS_PRESENT = {bool(before.get('acs_username')) or bool(before.get('acs_password'))}")
    print(f"TR069_REQUEST_CREDENTIALS_PRESENT = {bool(before.get('req_username')) or bool(before.get('req_password'))}")

    response = client.call("tr069", "set_config", data=copy.deepcopy(before))
    after = _subset(client.call("tr069", "get_config"), keys)
    same = after == before
    print(f"TR069_SAME_STATE_RESULT = {_result(response)!r}")
    print(f"TR069_SAME_STATE_READBACK = {same}")
    if _result(response) != 0 or not same:
        raise RuntimeError("TR069 same-state write failed")

    xmpp = client.call("tr069", "get_xmpp_config")
    servers = xmpp.get("server")
    print(f"XMPP_READ_RESULT = {_result(xmpp)!r}")
    print(f"XMPP_ENABLED = {xmpp.get('enable') == 1}")
    print(f"XMPP_SERVER_COUNT = {len(servers) if isinstance(servers, list) else 0}")
    print("XMPP_WRITE = SKIPPED_KNOWN_LIVE_REJECTED_RESULT_MINUS_1001")


def _vpn_items(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = response.get("vpn_clients")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _vpn_find_by_name(response: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    for item in _vpn_items(response):
        if str(item.get("vpn_name", "")) == name:
            return item
    return None


def _vpn_index(item: Mapping[str, Any]) -> str:
    raw = item.get("index")
    if raw is None:
        raise RuntimeError("VPN item index missing")
    return str(raw)


def _vpn_phase(client: NR2301Client) -> None:
    before = client.call("cm", "get_vpn_clients")
    before_items = copy.deepcopy(before.get("vpn_clients", []))
    before_enable = str(before.get("vpn_client_enable", ""))
    before_active = str(before.get("vpn_client_active_index", ""))
    before_status = client.call("cm", "get_vpn_client_connect_status")

    print(f"VPN_INITIAL_PROFILE_COUNT = {len(_vpn_items(before))}")
    print(f"VPN_GLOBAL_ENABLE_TOKEN_VALID = {before_enable in {'enable', 'disable'}}")
    print(f"VPN_ACTIVE_INDEX_PRESENT = {bool(before_active) and before_active not in {'-1', 'none'}}")
    print(f"VPN_STATUS_PRESENT = {isinstance(before_status.get('vpn_status'), str)}")
    if before_enable not in {"enable", "disable"}:
        raise RuntimeError("unexpected VPN global enable token")

    # Keep the synthetic lifecycle disconnected. If VPN was enabled, disable it
    # first and restore the exact original token in finally.
    synthetic_indexes: list[str] = []
    synthetic_names: list[str] = []
    original_active_restorable = any(
        str(item.get("index", "")) == before_active for item in _vpn_items(before)
    )

    try:
        disable = client.call(
            "cm", "open_close_vpn_clients", data={"vpn_client_enable": "disable"}
        )
        disabled_state = client.call("cm", "get_vpn_clients")
        disabled = str(disabled_state.get("vpn_client_enable", "")) == "disable"
        print(f"VPN_DISABLE_FOR_TEST_RESULT = {_result(disable)!r}")
        print(f"VPN_DISABLED_FOR_TEST = {disabled}")
        if not disabled:
            raise RuntimeError("VPN could not be disabled for synthetic lifecycle")

        suffix = uuid.uuid4().hex[:6]
        protocols = (
            ("pptp", ""),
            ("l2tp", ""),
            ("l2tp/ipsec", "sdk-probe-psk"),
        )
        for number, (protocol, secure) in enumerate(protocols, start=1):
            name = f"{TEST_VPN_PREFIX}{number}-{suffix}"
            payload = {
                "index": "-1",
                "vpn_name": name,
                "protocol_type": protocol,
                "vpn_server": TEST_VPN_SERVER,
                "vpn_user_name": TEST_VPN_USER,
                "vpn_user_password": TEST_VPN_PASSWORD,
                "vpn_secure": secure,
            }
            response = client.call("cm", "add_vpn_client_item", data=payload)
            current = client.call("cm", "get_vpn_clients")
            item = _vpn_find_by_name(current, name)
            visible = item is not None
            print(f"VPN_ADD_{number}_RESULT = {_result(response)!r}")
            print(f"VPN_ADD_{number}_READBACK = {visible}")
            if _result(response) != 0 or item is None:
                raise RuntimeError("VPN synthetic add failed")
            synthetic_indexes.append(_vpn_index(item))
            synthetic_names.append(name)

        # Edit the first synthetic item using the documented exact edit schema.
        current = client.call("cm", "get_vpn_clients")
        first = _vpn_find_by_name(current, synthetic_names[0])
        if first is None:
            raise RuntimeError("first synthetic VPN item disappeared")
        edited_name = f"{synthetic_names[0]}-EDIT"
        edit_payload = {
            "index": _vpn_index(first),
            "vpn_name": edited_name,
            "protocol_type": "pptp",
            "vpn_server": TEST_VPN_SERVER,
            "vpn_user_name": TEST_VPN_USER,
            "vpn_user_password": TEST_VPN_PASSWORD,
            "vpn_secure": "",
        }
        edit = client.call("cm", "edit_vpn_client_item", data=edit_payload)
        edited = _vpn_find_by_name(client.call("cm", "get_vpn_clients"), edited_name)
        print(f"VPN_EDIT_RESULT = {_result(edit)!r}")
        print(f"VPN_EDIT_READBACK = {edited is not None}")
        if _result(edit) != 0 or edited is None:
            raise RuntimeError("VPN synthetic edit failed")
        synthetic_names[0] = edited_name

        # Active/inactive semantics are tested only while global VPN is disabled,
        # so the synthetic endpoint cannot take over router traffic.
        active_index = synthetic_indexes[0]
        active = client.call(
            "cm",
            "active_vpn_client_item",
            data={"index": active_index, "vpn_active": "active"},
        )
        active_state = client.call("cm", "get_vpn_clients")
        active_visible = str(active_state.get("vpn_client_active_index", "")) == active_index
        print(f"VPN_ACTIVE_RESULT = {_result(active)!r}")
        print(f"VPN_ACTIVE_READBACK = {active_visible}")
        if _result(active) != 0 or not active_visible:
            raise RuntimeError("VPN active selection failed")

        inactive = client.call(
            "cm",
            "active_vpn_client_item",
            data={"index": active_index, "vpn_active": "inactive"},
        )
        inactive_state = client.call("cm", "get_vpn_clients")
        inactive_visible = str(inactive_state.get("vpn_client_active_index", "")) != active_index
        print(f"VPN_INACTIVE_RESULT = {_result(inactive)!r}")
        print(f"VPN_INACTIVE_READBACK = {inactive_visible}")
        if _result(inactive) != 0 or not inactive_visible:
            raise RuntimeError("VPN inactive selection failed")

        # If initial state was globally disabled, also prove the enable token with
        # no synthetic item active, then immediately return to disabled.
        if before_enable == "disable":
            enable = client.call(
                "cm", "open_close_vpn_clients", data={"vpn_client_enable": "enable"}
            )
            enabled = str(client.call("cm", "get_vpn_clients").get("vpn_client_enable", "")) == "enable"
            print(f"VPN_ENABLE_TOKEN_RESULT = {_result(enable)!r}")
            print(f"VPN_ENABLE_TOKEN_READBACK = {enabled}")
            if not enabled:
                raise RuntimeError("VPN enable token failed")
            client.call(
                "cm", "open_close_vpn_clients", data={"vpn_client_enable": "disable"}
            )
    finally:
        # Remove every synthetic profile by current name/index evidence. Never
        # touch a pre-existing profile.
        current = client.call("cm", "get_vpn_clients")
        for name in list(synthetic_names):
            item = _vpn_find_by_name(current, name)
            if item is None:
                continue
            index = _vpn_index(item)
            client.call("cm", "del_vpn_client_item", data={"index": index})
            current = client.call("cm", "get_vpn_clients")

        # Restore original active selection before restoring global enable state.
        if original_active_restorable and before_active:
            client.call(
                "cm",
                "active_vpn_client_item",
                data={"index": before_active, "vpn_active": "active"},
            )

        restore_global = client.call(
            "cm",
            "open_close_vpn_clients",
            data={"vpn_client_enable": before_enable},
        )
        final = client.call("cm", "get_vpn_clients")
        final_items = final.get("vpn_clients", [])
        count_restored = len(_vpn_items(final)) == len(_vpn_items(before))
        enable_restored = str(final.get("vpn_client_enable", "")) == before_enable
        active_restored = str(final.get("vpn_client_active_index", "")) == before_active
        profiles_exact = final_items == before_items
        print(f"VPN_GLOBAL_RESTORE_RESULT = {_result(restore_global)!r}")
        print(f"VPN_PROFILE_COUNT_RESTORED = {count_restored}")
        print(f"VPN_GLOBAL_ENABLE_RESTORED = {enable_restored}")
        print(f"VPN_ACTIVE_INDEX_RESTORED = {active_restored}")
        print(f"VPN_PROFILE_LIST_EXACT_RESTORED = {profiles_exact}")
        if not (count_restored and enable_restored and active_restored and profiles_exact):
            raise RuntimeError("VPN exact restore failed")


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
        timeout=12.0,
    ) as client:
        client.login()
        print("SENSITIVE_OUTPUT_POLICY = COUNTS_AND_BOOLEANS_ONLY")

        _phase("WAN", lambda: _wan_phase(client), failures)
        _phase("DDNS", lambda: _ddns_phase(client), failures)
        _phase("TR069", lambda: _tr069_phase(client), failures)
        _phase("VPN", lambda: _vpn_phase(client), failures)

    print(f"CONFIG_CAMPAIGN_FAILURE_COUNT = {len(failures)}")
    print(f"CONFIG_CAMPAIGN_FAILURES = {','.join(failures) if failures else '<none>'}")
    print(f"CONFIG_CAMPAIGN = {'PASS' if not failures else 'PARTIAL'}")


if __name__ == "__main__":
    main()
