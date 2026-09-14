# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os

from nr2301 import NR2301Client


def _require_integration_gate() -> None:
    if not any(
        os.environ.get(name) == "1"
        for name in (
            "NR2301_INTEGRATION",
            "NR2301_WRITE_INTEGRATION",
            "NR2301_DESTRUCTIVE_INTEGRATION",
        )
    ):
        raise RuntimeError(
            "NR2301_INTEGRATION=1 (or a stronger physical-test gate) is required"
        )


def _read_filter_all(client: NR2301Client, *, kind: str) -> object:
    if kind == "ip":
        return client.call(
            "firewall",
            "ww_read_ip_filter",
            data={"ww_ip_filter": {"list": ["all"]}},
        )
    if kind == "port":
        return client.call(
            "firewall",
            "ww_read_port_filter",
            data={"ww_port_filter": {"list": ["all"]}},
        )
    raise ValueError(f"unsupported filter kind: {kind}")


def capture(client: NR2301Client) -> dict[str, object]:
    """Capture the full local Firewall/NAT state needed for WebUI correlation.

    The result is intentionally unredacted for local physical research. Do not
    commit captured output from a real device to this public repository.
    """

    return {
        "disable_info": client.firewall.disable_info(),
        "dmz_info": client.firewall.dmz_info(),
        "admin_from_wan": client.firewall.admin_from_wan(),
        "ping_from_wan": client.firewall.ping_from_wan(),
        "vpn_passthrough": client.firewall.vpn_passthrough(),
        "upnp_state": client.firewall.upnp_state(),
        "ip_filter_mode_state": client.firewall.ip_filter_mode_state(),
        "ip_filter_all": _read_filter_all(client, kind="ip"),
        "port_filter_mode_state": client.firewall.port_filter_mode_state(),
        "port_filter_all": _read_filter_all(client, kind="port"),
        "url_filter": client.firewall.url_filter(),
        "port_forward": client.firewall.port_forward(),
        "port_trigger": client.firewall.port_trigger(),
    }


def main() -> None:
    _require_integration_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    label = os.environ.get("NR2301_SNAPSHOT_LABEL", "manual")
    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        snapshot = capture(client)

    print("FIREWALL_WEBUI_SNAPSHOT_BEGIN")
    print(f"SNAPSHOT_LABEL = {label}")
    print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
    print("FIREWALL_WEBUI_SNAPSHOT_END")


if __name__ == "__main__":
    main()
