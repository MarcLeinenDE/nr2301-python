# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


CLEAR_DMZ_VALUES = (None, "", "none")


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


def _blank_url_slots() -> list[dict[str, Any]]:
    return [{"value": "", "index": index} for index in range(10)]


def _xml_setting_response(text: str) -> str | None:
    if not text.strip():
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    node = root.find(".//setting_response")
    return node.text if node is not None else None


def _xml_delete_dmz(client: NR2301Client) -> tuple[int, str | None, int]:
    # Exact no-argument PostXml shape reconstructed from the Marvell WebUI.
    xml_body = (
        '<?xml version="1.0" encoding="US-ASCII"?> '
        '<RGW><param><method>call</method><session>000</session>'
        '<obj_path>firewall</obj_path><obj_method>delete_dmz</obj_method>'
        '</param></RGW>'
    )
    response = client.transport.session.post(
        f"{client.transport.base_url}/xml_action.cgi?method=set",
        data=xml_body.encode("ascii"),
        headers={"Content-Type": "text/xml;charset=UTF-8"},
        timeout=10.0,
        allow_redirects=False,
    )
    return response.status_code, _xml_setting_response(response.text), len(response.content)


def main() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    dmz_ok = False
    url_ok = False

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()

        # ----- DMZ recovery -----
        disable_before = _find_value(client.firewall.disable_info(), "dmz_disable")
        dest_before = _find_value(client.firewall.dmz_info(), "dmz_dest_ip")
        print("DMZ_DISABLE_BEFORE =", repr(disable_before))
        print("DMZ_DEST_BEFORE_CLASS =", "CLEAR" if dest_before in CLEAR_DMZ_VALUES else "SET")

        if dest_before in CLEAR_DMZ_VALUES:
            print("DMZ_XML_DELETE = SKIPPED_ALREADY_CLEAR")
        else:
            status, setting_response, body_length = _xml_delete_dmz(client)
            print("DMZ_XML_HTTP_STATUS =", status)
            print("DMZ_XML_SETTING_RESPONSE =", repr(setting_response))
            print("DMZ_XML_BODY_LENGTH =", body_length)

        disable_after = _find_value(client.firewall.disable_info(), "dmz_disable")
        dest_after = _find_value(client.firewall.dmz_info(), "dmz_dest_ip")
        dmz_clear = dest_after in CLEAR_DMZ_VALUES
        disable_unchanged = disable_after == disable_before
        dmz_ok = dmz_clear and disable_unchanged
        print("DMZ_DEST_AFTER_CLASS =", "CLEAR" if dmz_clear else "SET")
        print("DMZ_DISABLE_UNCHANGED =", disable_unchanged)
        print("DMZ_RECOVERY_OK =", dmz_ok)

        # ----- URL-filter recovery -----
        before = client.firewall.url_filter()
        before_settings = _find_mapping(before, "settings") or {}
        before_black = before_settings.get("black_items")
        before_white = before_settings.get("white_items")
        print("URL_MODE_BEFORE =", repr(before_settings.get("mode")))
        print("URL_BLACK_NONEMPTY_BEFORE =", _nonempty_indexed_count(before_black))
        print("URL_WHITE_NONEMPTY_BEFORE =", _nonempty_indexed_count(before_white))

        blank_black = _blank_url_slots()
        blank_white = _blank_url_slots()

        active_clear = client.call(
            "firewall",
            "set_url_filter",
            data={
                "mode": "blacklist",
                "black_items": blank_black,
                "white_items": blank_white,
            },
        )
        print("URL_ACTIVE_CLEAR_RESULT =", active_clear.get("result"))

        active_read = client.firewall.url_filter()
        active_settings = _find_mapping(active_read, "settings") or {}
        active_black_count = _nonempty_indexed_count(active_settings.get("black_items"))
        active_white_count = _nonempty_indexed_count(active_settings.get("white_items"))
        print("URL_ACTIVE_MODE_AFTER =", repr(active_settings.get("mode")))
        print("URL_ACTIVE_BLACK_NONEMPTY_AFTER =", active_black_count)
        print("URL_ACTIVE_WHITE_NONEMPTY_AFTER =", active_white_count)

        disable_write = client.call(
            "firewall",
            "set_url_filter",
            data={
                "mode": "disable",
                "black_items": blank_black,
                "white_items": blank_white,
            },
        )
        print("URL_DISABLE_RESULT =", disable_write.get("result"))

        final = client.firewall.url_filter()
        final_settings = _find_mapping(final, "settings") or {}
        final_black_count = _nonempty_indexed_count(final_settings.get("black_items"))
        final_white_count = _nonempty_indexed_count(final_settings.get("white_items"))
        final_mode = final_settings.get("mode")
        url_ok = final_mode == "disable" and final_black_count == 0 and final_white_count == 0
        print("URL_MODE_AFTER =", repr(final_mode))
        print("URL_BLACK_NONEMPTY_AFTER =", final_black_count)
        print("URL_WHITE_NONEMPTY_AFTER =", final_white_count)
        print("URL_RECOVERY_OK =", url_ok)

    print("FIREWALL_NAT_RECOVERY_V4 =", "PASS" if dmz_ok and url_ok else "PARTIAL")


if __name__ == "__main__":
    main()
