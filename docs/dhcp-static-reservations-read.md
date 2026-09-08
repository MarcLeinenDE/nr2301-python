# DHCP static-reservation read coverage

This SDK block exposes only the already live-verified normal-admin read contract `router/router_get_dhcp_static_ip` as `client.lan.static_reservations()`.

## Scope

- SDK helper: `client.lan.static_reservations()`
- API method: `router/router_get_dhcp_static_ip`
- transport: GET, no request body
- the complete firmware JSON response is preserved raw

The upstream public contract intentionally does not freeze a stable nested schema for this response, so the SDK does not invent reservation field names or normalize the returned structure.

The SDK deliberately does **not** expose or exercise `router/router_set_dhcp_static_ip` in this block.

## Privacy

DHCP reservations can contain private LAN addresses and device MAC addresses. The physical smoke validates only that the helper returns a mapping and does not print or assert concrete reservation values.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

The targeted read-only LAN/DNS integration selection exercised the existing LAN/DNS reads plus `client.lan.static_reservations()` and completed successfully:

```text
1 passed, 10 deselected in 0.92 s
```

No DHCP/LAN configuration write occurred, and no reservation IP/MAC values were printed.

No `nr2301-api` change was required by this run because `router/router_get_dhcp_static_ip` was already `LIVE_VERIFIED`, `ADMIN_OK` and `READ_OR_LOW_SIDE_EFFECT`; this adds public-SDK physical-path evidence only.
