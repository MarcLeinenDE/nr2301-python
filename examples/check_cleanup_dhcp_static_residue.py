# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time

from nr2301 import NR2301Client, NR2301Error


SYNTHETIC_MACS = {
    "02:00:00:00:00:fe",
    "02:00:00:00:00:fd",
    "02:00:00:00:00:fc",
}


def normalized_mac(value):
    return str(value).replace("-", ":").lower()


def is_synthetic(item):
    return normalized_mac(item["mac"]) in SYNTHETIC_MACS


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

        synthetic_present = any(is_synthetic(item) for item in current)
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

        # The integration probe starts from an empty reservation table and
        # uses only the reserved locally-administered synthetic MACs above.
        # Clear only when one such test reservation is the sole current entry.
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
