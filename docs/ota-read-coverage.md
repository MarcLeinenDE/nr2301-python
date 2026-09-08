# OTA read-only coverage

This SDK block exposes only the two OTA state/status contracts that are already normalized upstream as normal-admin read/low-side-effect operations.

## High-level helpers

| SDK helper | API method | Transport |
|---|---|---|
| `client.ota.updated_status()` | `ota/get_updated_status` | GET, no body |
| `client.ota.query_state()` | `ota/new_query` | POST with exactly `{"type": 1}` |

Both helpers preserve the firmware response as raw strings. In particular, `query_state().response == "idle"` is **not** interpreted as proof that the firmware is current. Upstream research documents `idle` as context-dependent; the stock WebUI performs a separate `manual_check_update` flow and polls before presenting a no-update message.

## Explicit exclusions

This block does **not** expose or exercise:

- `ota/manual_check_update`
- `ota/download_update`
- `ota/clear_failed_state`
- `ota/abandon_checked`
- `ota/abandon_download_update`

Therefore the physical smoke does not start a firmware check, download, install, failed-state clear or cancellation action.

## Physical evidence — 2026-09-08

Test target: Zyxel NR2301, tested firmware family ACIY.3.

Targeted command selected only `test_ota_reads` from the read-only integration suite.

Result:

```text
1 passed, 10 deselected in 0.47s
```

The test exercised both public SDK helpers through an authenticated normal-admin session and asserted only response shape. It printed no release notes or router configuration data and performed no OTA mutation.

No upstream `nr2301-api` contract change was required by this run: both wire contracts were already `LIVE_VERIFIED`; this test adds public-SDK physical-path evidence only.
