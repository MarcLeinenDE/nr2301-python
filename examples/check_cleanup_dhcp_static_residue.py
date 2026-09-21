# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time

from nr2301 import NR2301Client, NR2301Error


SYNTHETIC = {
    "index": "0",
    "mac": "02:00:00:00:00:fe",
    "ip": "192.0.2.254",
}


def fingerprint(item):
    return (
        str(item["index"]),
        str(item["mac"]).lower(),
        str(item["ip"]),
    )


def main() -> None:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        current = client.lan.static_reservation_list(timeout=5.0)

        synthetic_present = any(
            fingerprint(item) == fingerprint(SYNTHETIC)
            for item in current
        )
        print(
            "DHCP_STATIC_RESIDUE"
            f" count={len(current)}"
            f" synthetic_present={synthetic_present}"
        )

        if not synthetic_present:
            print("DHCP_STATIC_RESIDUE_CLEANUP = NOT_NEEDED")
            return

        if len(current) != 1:
            raise RuntimeError(
                "synthetic reservation is present together with other entries; "
                "refusing automatic cleanup"
            )

        # The failed integration test started from an empty reservation table.
        # Clear only the exact sole synthetic residue using the already
        # historically live-verified empty-table restore shape.
        try:
            client.multicall(
                [
                    {
                        "path": "router",
                        "method": "router_set_dhcp_static_ip",
                        "data": {"data": []},
                        "timeout": 30,
                    }
                ],
                timeout=30.0,
            )
        except NR2301Error:
            pass

        for attempt in range(30):
            try:
                after = client.lan.static_reservation_list(timeout=4.0)
                if not after:
                    print("DHCP_STATIC_RESIDUE_CLEANUP = PASS")
                    return
            except NR2301Error:
                try:
                    client.login()
                except NR2301Error:
                    pass
            if attempt < 29:
                time.sleep(1.0)

        raise RuntimeError("synthetic DHCP reservation residue could not be cleared")


if __name__ == "__main__":
    main()
