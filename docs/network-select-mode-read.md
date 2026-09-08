# WAN network selection mode read coverage

This SDK block exposes only the already live-verified normal-admin read contract `util_wan/get_network_select_mode` as `client.mobile.network_select_mode()`.

## Scope

- SDK helper: `client.mobile.network_select_mode()`
- API method: `util_wan/get_network_select_mode`
- transport: GET, no request body
- response fields are preserved raw: `nw_sel_mode`, `result`

This block deliberately does **not** expose or exercise:

- `util_wan/search_network` — operator scan; current upstream auth evidence is still `UNTESTED`
- `util_wan/select_network` — manual network selection; classified `DISRUPTIVE_RECOVERY_REQUIRED`

The SDK does not invent semantic aliases for `nw_sel_mode`; callers receive the firmware's raw value.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

The targeted read-only integration selection exercised the existing mobile reads plus `client.mobile.network_select_mode()` and completed successfully:

```text
1 passed, 10 deselected in 0.61s
```

No operator scan, network-selection write or connectivity transition was performed.

No `nr2301-api` change was required by this run because `util_wan/get_network_select_mode` was already `LIVE_VERIFIED`, `ADMIN_OK` and `READ_OR_LOW_SIDE_EFFECT`; this adds public-SDK physical-path evidence only.
