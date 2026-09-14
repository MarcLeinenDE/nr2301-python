# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


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


def _nonempty_indexed_count(value: object) -> int:
    if not isinstance(value, list):
        return 0
    count = 0
    for item in value:
        if not isinstance(item, Mapping):
            continue
        raw = item.get("value")
        if isinstance(raw, str) and raw:
            count += 1
    return count


def _setting_response(response: Mapping[str, Any]) -> object | None:
    return _find_value(response, "setting_response")


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

        disable_before = _find_value(client.firewall.disable_info(), "dmz_disable")
        dest_before = _find_value(client.firewall.dmz_info(), "dmz_dest_ip")
        print("DMZ_DISABLE_BEFORE =", repr(disable_before))
        print("DMZ_DEST_PRESENT_BEFORE =", isinstance(dest_before, str) and bool(dest_before))

        if isinstance(dest_before, str) and dest_before:
            response = client.call("firewall", "delete_dmz")
            print("DMZ_DELETE_SETTING_RESPONSE =", repr(_setting_response(response)))
        else:
            print("DMZ_DELETE_SETTING_RESPONSE = SKIPPED_ALREADY_EMPTY")

        disable_after = _find_value(client.firewall.disable_info(), "dmz_disable")
        dest_after = _find_value(client.firewall.dmz_info(), "dmz_dest_ip")
        dmz_empty = dest_after in (None, "")
        dmz_disable_unchanged = disable_after == disable_before
        print("DMZ_DEST_EMPTY_AFTER =", dmz_empty)
        print("DMZ_DISABLE_UNCHANGED =", dmz_disable_unchanged)

        url = client.firewall.url_filter()
        settings = _find_mapping(url, "settings") or {}
        black = settings.get("black_items")
        white = settings.get("white_items")
        print("URL_MODE =", repr(settings.get("mode")))
        print("URL_BLACK_SLOT_COUNT =", len(black) if isinstance(black, list) else 0)
        print("URL_WHITE_SLOT_COUNT =", len(white) if isinstance(white, list) else 0)
        print("URL_BLACK_NONEMPTY_COUNT =", _nonempty_indexed_count(black))
        print("URL_WHITE_NONEMPTY_COUNT =", _nonempty_indexed_count(white))

        if not dmz_empty:
            raise RuntimeError("DMZ recovery did not restore the empty destination state")
        if not dmz_disable_unchanged:
            raise RuntimeError("DMZ recovery unexpectedly changed the enable/disable state")

        print("FIREWALL_NAT_RECOVERY = PASS")


if __name__ == "__main__":
    main()
