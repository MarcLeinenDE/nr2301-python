# SPDX-License-Identifier: GPL-3.0-or-later
"""Print a sanitized NR2301 Wi-Fi capability/configuration snapshot.

This tool is read-only. It intentionally removes SSIDs, keys, MAC-like values and
other identity/credential material from its output. The remaining values are
useful for building evidence-backed reversible Wi-Fi write tests.

Environment:
    NR2301_PASSWORD  required
    NR2301_URL       optional, defaults to http://zyxel.home
    NR2301_USERNAME  optional, defaults to admin
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client

SENSITIVE_KEYS = {
    "ssid",
    "key",
    "password",
    "pwd",
    "bssid",
    "mac",
    "macaddr",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in SENSITIVE_KEYS or lowered.endswith("_mac"):
                out[str(key)] = "<redacted>"
            else:
                out[str(key)] = sanitize(item)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def main() -> None:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    base_url = os.environ.get("NR2301_URL", "http://zyxel.home")
    username = os.environ.get("NR2301_USERNAME", "admin")

    with NR2301Client(base_url, username=username, password=password) as router:
        router.login()
        ap = router.wifi.config()
        basic = router.wifi.basic_info()
        timed = router.wifi.timed_off_status()
        diagnostics = router.wifi.diagnostics()

        snapshot = {
            "management_url": base_url,
            "ap_config": sanitize(ap),
            "basic_info": sanitize(basic),
            "timed_off_status": sanitize(timed),
            "diagnostics": sanitize(diagnostics),
        }

    print("NR2301 sanitized Wi-Fi capability snapshot")
    print("No Wi-Fi SSID/key or password values are printed.")
    print(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
