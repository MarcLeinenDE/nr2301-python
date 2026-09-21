# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os

from nr2301 import NR2301Client


def main() -> None:
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
        response = client.device.work_mode(timeout=5.0)

    print(
        "WORK_MODE_RESPONSE = "
        + json.dumps(response, ensure_ascii=True, sort_keys=True)
    )


if __name__ == "__main__":
    main()
