# Physical-router integration testing

This repository keeps ordinary `pytest` runs offline. Tests that touch a real NR2301 are explicitly opt-in and split by risk.

## Environment

The tested management endpoint is the canonical host:

```text
http://zyxel.home
```

On tested firmware `V1.00(ACIY.3)C0`, direct `http://192.168.1.1` administrator pre-auth calls can return `result=4` even though `zyxel.home` resolves to the same address. Use the canonical host for the physical suite.

Required variables:

```text
NR2301_PASSWORD
```

Optional variables:

```text
NR2301_URL       (default: http://zyxel.home)
NR2301_USERNAME  (default: admin)
```

Never commit the real administrator password or pass it on the command line where shell history/process inspection can expose it.

## Risk tiers

### Read-only

Enable with:

```text
NR2301_INTEGRATION=1
```

Read-only tests are intended for status/configuration retrieval only. They deliberately avoid printing high-sensitivity identifiers, Wi-Fi credentials, SMS content, package usage/quota values, firewall/NAT rules and similar private state when that data is not needed to prove the contract.

The read-only suite currently includes targeted groups for version/device/SIM/mobile/LAN/Wi-Fi/SMS/statistics/package/firewall and OTA state/status reads.

### Reversible write

Enable with:

```text
NR2301_WRITE_INTEGRATION=1
```

A reversible test must snapshot the exact original state, write only a controlled temporary value, require read-back, restore in `finally`, and verify the restored state. Tests should avoid using the last remaining SIM PIN/PUK attempt or any other recovery resource solely for coverage.

Current reversible examples include data roaming, router-advertised network mode, WPS enable/actions, Guest/combined-vs-separate Wi-Fi modes, DNS, auto-sleep timeout, timed reboot schedules and UI language.

### Destructive / recovery

Destructive actions require a dedicated explicit gate and recovery plan. They are not enabled by ordinary CI or the read-only/write flags above. USB-management-mode mutation remains excluded while USB is the active control/recovery channel.

Do not trigger firmware installation, factory reset, SIM blocking or other destructive transitions merely to improve test coverage.

## Read-only OTA evidence — 2026-09-08

The targeted OTA smoke selected only `test_ota_reads` and passed against the physical ACIY.3 router:

```text
1 passed, 10 deselected in 0.47s
```

It exercised exactly:

- `ota/get_updated_status` as a body-less GET through `client.ota.updated_status()`
- `ota/new_query` as POST `{"type": 1}` through `client.ota.query_state()`

The run did **not** call `manual_check_update`, `download_update`, `clear_failed_state`, `abandon_checked` or `abandon_download_update`. Therefore it did not start a firmware check, download, install, failed-state clear or cancellation action.

`query_state()` preserves raw firmware state. In particular, `idle` is not normalized to “firmware current”; upstream evidence documents that interpretation as context-dependent.

See [`ota-read-coverage.md`](ota-read-coverage.md) for the focused contract/evidence note.
