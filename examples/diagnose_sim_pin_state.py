# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only, sanitized SIM PIN/PUK state preflight for a physical NR2301.

This helper deliberately prints only SIM/PIN state and retry counters. It never
reads or prints device identity information and does not accept PIN/PUK values.
"""

from __future__ import annotations

import json
import os
from typing import Any

from nr2301 import NR2301Client


def main() -> int:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    client = NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
    )
    try:
        client.login()
        response = client.sim.status()
        pin_puk = response.get("pin_puk")
        if not isinstance(pin_puk, dict):
            raise RuntimeError("sim/get_sim_status returned no pin_puk mapping")

        safe: dict[str, Any] = {
            "sim_status": pin_puk.get("sim_status"),
            "pin_status": pin_puk.get("pin_status"),
            "pin_enabled": pin_puk.get("pin_enabled"),
            "pin_attempts": pin_puk.get("pin_attempts"),
            "puk_attempts": pin_puk.get("puk_attempts"),
        }
        setting = response.get("response")
        if isinstance(setting, dict):
            safe["setting_response"] = setting.get("setting_response")

        print("NR2301 sanitized SIM PIN state preflight")
        print("Read-only: no PIN/PUK is requested, transmitted or printed.")
        print("No ICCID/IMSI/IMEI or other subscriber/device identifier is read.")
        print(json.dumps(safe, indent=2, ensure_ascii=False))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
