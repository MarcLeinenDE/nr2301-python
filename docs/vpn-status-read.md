# VPN connection-status read coverage

This SDK block exposes only the already live-verified normal-admin status contract `cm/get_vpn_client_connect_status` as `client.vpn.status()`.

## Scope

- SDK helper: `client.vpn.status()`
- API method: `cm/get_vpn_client_connect_status`
- transport: GET, no request body
- response fields preserved raw: `result`, `vpn_status`

The SDK deliberately does **not** call or expose `cm/get_vpn_clients` in this block. That profile-list response may contain VPN passwords or PSKs and is therefore unsuitable for routine diagnostics or a generic read-only smoke test.

No VPN add/edit/delete/activate/connect/disconnect action is part of this block.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

The targeted read-only integration selection completed successfully:

```text
1 passed, 11 deselected in 0.44 s
```

Only `client.vpn.status()` / `cm/get_vpn_client_connect_status` was exercised. No VPN profile was read, no credential-bearing response was requested, and no VPN connection or configuration state was changed.

No `nr2301-api` change was required by this run because `cm/get_vpn_client_connect_status` was already `LIVE_VERIFIED`, `ADMIN_OK` and `READ_OR_LOW_SIDE_EFFECT`; this adds public-SDK physical-path evidence only.
