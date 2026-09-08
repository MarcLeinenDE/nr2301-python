# Router work-mode read coverage

This SDK block exposes only the already live-verified normal-admin read contract `router/router_get_work_mode` as `client.device.work_mode()`.

## Scope

- SDK helper: `client.device.work_mode()`
- API method: `router/router_get_work_mode`
- transport: GET, no request body
- response fields are preserved raw: `mode`, `result`
- source-known normal values are `router` and `bridge`

The SDK deliberately does **not** expose or exercise `router/router_set_work_mode` in this block. Changing work mode is classified upstream as `DISRUPTIVE_RECOVERY_REQUIRED` and may change management connectivity.

Unknown future raw `mode` values are returned unchanged rather than coerced into the source-known pair.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

The targeted read-only device-health integration selection exercised the existing safe device reads plus `client.device.work_mode()` and completed successfully:

```text
1 passed, 10 deselected in 3.43s
```

No work-mode write, bridge transition, reboot or connectivity mutation was performed.

No `nr2301-api` change was required by this run because `router/router_get_work_mode` was already `LIVE_VERIFIED`, `ADMIN_OK` and `READ_OR_LOW_SIDE_EFFECT`; this adds public-SDK physical-path evidence only.
