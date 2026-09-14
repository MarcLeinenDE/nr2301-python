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


def _nonempty_count(value: object) -> int:
    if not isinstance(value, list):
        return 0
    return sum(
        1
        for item in value
        if isinstance(item, Mapping)
        and isinstance(item.get("value"), str)
        and bool(item.get("value"))
    )


def _dmz_is_clear(value: object) -> bool:
    return value in (None, "", "none")


def _empty_url_slots() -> list[dict[str, object]]:
    return [{"value": "", "index": index} for index in range(10)]


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
        print("DMZ_DEST_BEFORE_CLASS =", "CLEAR" if _dmz_is_clear(dest_before) else "SET")

        if not _dmz_is_clear(dest_before):
            # No-argument write action: force POST by sending an empty JSON object.
            response = client.transport.session.post(
                client.transport.api_url,
                params={
                    "path": "firewall",
                    "method": "delete_dmz",
                    "timeout": "10",
                },
                json={},
                timeout=10.0,
            )
            print("DMZ_DELETE_POST_HTTP_STATUS =", response.status_code)
            print("DMZ_DELETE_POST_BODY_LENGTH =", len(response.content))
            response.raise_for_status()
        else:
            print("DMZ_DELETE_POST_HTTP_STATUS = SKIPPED_ALREADY_CLEAR")

        dest_after = _find_value(client.firewall.dmz_info(), "dmz_dest_ip")
        disable_after = _find_value(client.firewall.disable_info(), "dmz_disable")
        dmz_clear = _dmz_is_clear(dest_after)
        dmz_disable_unchanged = disable_after == disable_before
        print("DMZ_DEST_AFTER_CLASS =", "CLEAR" if dmz_clear else "SET")
        print("DMZ_DISABLE_UNCHANGED =", dmz_disable_unchanged)

        url_before = client.firewall.url_filter()
        settings_before = _find_mapping(url_before, "settings") or {}
        black_before = settings_before.get("black_items")
        white_before = settings_before.get("white_items")
        mode_before = settings_before.get("mode")
        print("URL_MODE_BEFORE =", repr(mode_before))
        print("URL_BLACK_SLOT_COUNT_BEFORE =", len(black_before) if isinstance(black_before, list) else 0)
        print("URL_BLACK_NONEMPTY_BEFORE =", _nonempty_count(black_before))
        print("URL_WHITE_NONEMPTY_BEFORE =", _nonempty_count(white_before))

        if _nonempty_count(black_before) or _nonempty_count(white_before):
            # The firmware treats [] as "leave existing fixed slots alone". Clear
            # all ten observed blacklist slots explicitly. Keep the disabled mode.
            response = client.call(
                "firewall",
                "set_url_filter",
                data={
                    "mode": "disable",
                    "black_items": _empty_url_slots(),
                    "white_items": [],
                },
            )
            print("URL_CLEAR_RESULT =", repr(response.get("result")))
        else:
            print("URL_CLEAR_RESULT = SKIPPED_ALREADY_EMPTY")

        url_after = client.firewall.url_filter()
        settings_after = _find_mapping(url_after, "settings") or {}
        black_after = settings_after.get("black_items")
        white_after = settings_after.get("white_items")
        mode_after = settings_after.get("mode")
        url_clear = _nonempty_count(black_after) == 0 and _nonempty_count(white_after) == 0
        print("URL_MODE_AFTER =", repr(mode_after))
        print("URL_BLACK_SLOT_COUNT_AFTER =", len(black_after) if isinstance(black_after, list) else 0)
        print("URL_BLACK_NONEMPTY_AFTER =", _nonempty_count(black_after))
        print("URL_WHITE_NONEMPTY_AFTER =", _nonempty_count(white_after))

        if not dmz_clear:
            raise RuntimeError("DMZ destination is still set after POST delete_dmz")
        if not dmz_disable_unchanged:
            raise RuntimeError("DMZ enable/disable state changed during recovery")
        if not url_clear:
            raise RuntimeError("URL filter still contains non-empty synthetic entries")

        print("FIREWALL_NAT_RECOVERY_V3 = PASS")


if __name__ == "__main__":
    main()
