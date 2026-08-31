# nr2301-python

Unofficial Python SDK for the local management API of the **Zyxel NR2301** mobile router.

This SDK is built against the independently reverse-engineered API reference published in [`MarcLeinenDE/nr2301-api`](https://github.com/MarcLeinenDE/nr2301-api). The initial development baseline is API release [`v0.1.0`](https://github.com/MarcLeinenDE/nr2301-api/releases/tag/v0.1.0); newly normalized contracts currently track API `main` development metadata `0.1.1.dev0` until the next API release.

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or supported by Zyxel. The NR2301 API is undocumented by the manufacturer and may change between firmware versions.

## Status

`0.1.0.dev0` is the current SDK development line. The long-term target is evidence-backed coverage of all locally usable NR2301 API capabilities, not just the feature set of the earlier private application. Safety classifications drive warnings/test gates/recovery behavior; downstream applications decide which SDK capabilities they expose.

Implemented so far:

- administrator challenge login (`account/get_rand` → MD5 challenge → `account/login`)
- `CGISID` session handling through `requests.Session`
- generic single-call and multicall API access
- explicit transport/protocol/authentication/API exceptions
- context-manager support
- typed read-only `version` helpers
- safe device/router health, battery, feature and identity reads
- safe SIM status plus documented raw-value summary labels
- safe traffic/client-statistics reads
- typed mobile-network reads plus verified network-mode/data-roaming writes
- LAN/DHCP/DNS reads plus verified DNS writes
- typed Wi-Fi/WPS/extender reads
- Wi-Fi AP-section writes, WPS enable/disable, combined ↔ separate SSID mode switching and Guest enable/disable with recovery/read-back
- SMS mailbox summary/list/query plus verified normal-SMS send and single-ID delete
- offline unit tests
- explicitly opt-in, read-only physical-router smoke tests
- GitHub Actions test matrix for Python 3.10–3.13

Planned next:

- continue physical coverage of reversible and disruptive API capabilities, including Wi-Fi field-level controls that the earlier private app did not implement
- close incomplete upstream contracts and expose every sufficiently evidenced local capability through the SDK
- keep feeding all physical findings back into `nr2301-api` before the first stable SDK release audit

## Install for development

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
pytest
```

Normal `pytest` runs are offline. Physical-router tests require an explicit opt-in; see [Physical-router integration testing](docs/integration-testing.md).

## Quick start

Do not hard-code router passwords in source code. This example reads the password from an environment variable.

```python
import os

from nr2301 import NR2301Client

with NR2301Client(
    "http://zyxel.home",
    username="admin",
    password=os.environ["NR2301_PASSWORD"],
) as router:
    router.login()

    print(router.version.info())
    print(router.device.runtime())
    print(router.sim.summary())
    print(router.mobile.cell_info())
    print(router.lan.dns())
    print(router.wifi.basic_info())
    print(router.sms.brief_info())
    print(router.statistics.traffic())
```

The generic transport remains available for every documented method:

```python
result = router.call(
    "account",
    "get_retrytimes_and_time",
    data={"type": "admin"},
    authenticated=False,
)
```

A call with no `data` argument uses HTTP GET, matching the observed stock frontend behavior. Supplying `data` uses HTTP POST with JSON.

## Device / router status

Safe status-oriented reads are grouped under `router.device`:

```python
print(router.device.runtime())
print(router.device.diagnostics())
print(router.device.internet())
print(router.device.features())
print(router.device.battery())
print(router.device.sleep_wait_time())
print(router.device.ui_language())
```

Additional identity surfaces are available when an application deliberately needs them:

```python
device = router.device.info()
macs = router.device.mac_info()
```

> [!CAUTION]
> `device.info()` can contain IMEI, IMSI, ICCID and serial number. `device.mac_info()` contains interface MAC addresses. Treat those values as sensitive identifiers and do not include them in public logs, fixtures or issue reports by default.

`device.internet()` preserves the documented raw `access` value (`1` available, `0` unavailable). Diagnostic level values are also returned raw rather than being silently remapped by the base SDK.

## SIM status

The safe SIM API is read-only:

```python
raw = router.sim.status()
summary = router.sim.summary()
print(summary)
```

`summary()` uses only the endpoint-scoped mappings documented by `nr2301-api`, for example:

- SIM status `0` = No SIM, `1` = SIM present, `2` = SIM error, `3` = Unknown SIM error
- PIN status `2` = PIN required, `3` = PUK required, `5` = Ready
- PIN enabled `0` = disabled, `1` = enabled

Unknown numeric values are preserved and displayed as `Unknown (<raw>)`; they are not coerced into a guessed state.

PIN/PUK writes are not exposed **yet** because their complete live contracts still need deliberate physical verification. They remain SDK coverage targets; retry-consuming tests require an explicit scenario and recovery plan rather than broad probing.

`sim/get_lock_info` is also not wrapped as a high-level helper because the tested firmware returned HTTP 200/application-json with a zero-length body rather than a stable JSON contract.

## Statistics / client state

Traffic counters and transport activity:

```python
print(router.statistics.traffic())
print(router.statistics.traffic_transport_status())
```

MAC-filter and management metadata:

```python
print(router.statistics.filter_mode())
print(router.statistics.login_client_mac())
```

The login-client MAC is diagnostic metadata only; the API research found that it is not reliable enough to be the sole identity proof for USB management.

A body-less client inventory read is available:

```python
clients = router.statistics.clients()
```

The underlying endpoint also supports frontend-specific `request_type` views. Until those exact raw tokens are normalized as a stable public contract, the SDK does not invent `active_clients()` / `inactive_clients()` / allow-list aliases. Advanced callers can pass an independently verified token through exactly:

```python
clients = router.statistics.clients(request_type="<verified raw request_type>")
```

No traffic-counter clear or MAC-filter write is part of this safe read namespace yet.

## Mobile network

Read cellular/WAN state and current settings:

```python
print(router.mobile.cell_info())
print(router.mobile.wan_info())
print(router.mobile.network_settings())
```

Ask the router for its actual network-mode strings before writing one:

```python
modes = router.mobile.available_network_modes().get("network_modes", [])
selected_mode = modes[0]
verified = router.mobile.set_network_mode(selected_mode)
```

`set_network_mode()` refuses values not reported by the target router, writes only `network_mode`, and requires exact read-back. Data roaming follows the same evidence-backed pattern:

```python
router.mobile.set_data_roaming(True)
router.mobile.set_data_roaming(False)
```

The public API contract does not fully reconstruct APN/profile writes through `cm/set_network_settings`, so this SDK does not invent them.

## LAN / DHCP / DNS

```python
dhcp = router.lan.dhcp()
dns = router.lan.dns()
address = router.lan.address()

verified = router.lan.set_dns(
    "1.1.1.1",
    "1.0.0.1",
    ipv6_primary="2606:4700:4700::1111",
    ipv6_secondary="2606:4700:4700::1001",
)

router.lan.set_dns_auto()
```

> [!WARNING]
> The NR2301 uses a combined LAN/DHCP/DNS setter that may reset management connectivity. The high-level DNS helper copies the complete current DHCP object, changes only DNS fields, writes it through multicall, then requires exact read-back.

The configured manual addresses are upstream resolvers for the NR2301 DNS proxy. Clients may still receive the router's LAN address as their DNS server.

## Wi-Fi / WPS / extender

Read state:

```python
print(router.wifi.config())
print(router.wifi.basic_info())
print(router.wifi.guest_enabled())
print(router.wifi.uses_separate_ssids())
print(router.wifi.wps())
print(router.wifi.extender_status())
```

Change one existing AP section while preserving the rest of that block:

```python
router.wifi.update_ap_section(
    "wifi_if_24G",
    {"ssid": "Example-SSID"},
)
```

### Combined vs separate 2.4/5 GHz settings

The tested firmware has four live-verified mode states:

```text
DUAL
DUAL GUEST
2.4G 5G
2.4G 5G GUEST
```

Switch the main Wi-Fi between a combined/shared 2.4/5 GHz SSID and separate band settings:

```python
router.wifi.set_separate_ssids(False)  # combined/shared main SSID
router.wifi.set_separate_ssids(True)   # separate 2.4 and 5 GHz settings
```

The helper preserves the current Guest token, carries forward all current participating AP blocks, handles an expected management reset, and requires exact mode read-back. `DUAL` is intentionally **not** labelled Band Steering because steering behavior was not separately proven.

### Guest Wi-Fi

Guest enable/disable is represented by the `GUEST` token in the Wi-Fi mode; the router has no separate Guest-enable property:

```python
router.wifi.set_guest_enabled(True)
router.wifi.set_guest_enabled(False)
```

The current Guest configuration is preserved and verified after recovery. Guest `maxassoc` can be changed through `update_ap_section()`; the tested/frontend-supported normal range is `1..10`.

> [!CAUTION]
> On tested firmware `V1.00(ACIY.3)C0`, the getter does not return an independently round-trippable Guest `isolate` value. The SDK therefore does not expose a separate Guest-isolation control.

WPS enable/disable remains available:

```python
router.wifi.set_wps_enabled(True)
router.wifi.set_wps_enabled(False)
```

> [!WARNING]
> Wi-Fi setters are disruptive. If the SDK itself is connected through the Wi-Fi network whose SSID/key/mode changes, the host operating system may need to reconnect before HTTP read-back can succeed. The SDK can recover HTTP sessions but cannot reconfigure the host operating system's Wi-Fi connection.

## SMS

Read mailbox state:

```python
summary = router.sms.brief_info()
page = router.sms.list_by_type(0, page_index=1)
ids = router.sms.query_ids(message_type=4, read=2, location=0)
```

Send a normal SMS using the exact live-verified stock-frontend encoding contract:

```python
result = router.sms.send("+15551234567", "Hello")
```

`send()` automatically:

- detects whether the message fits the frontend GSM7 character sets;
- converts the message to the router's UTF-16BE uppercase-hex `UniEncode` representation;
- creates the observed local timestamp format;
- adds the required trailing comma to the recipient field;
- uses the live-verified normal-SMS `protocol="0"` flow;
- requires `resp=0`, `smsSendSucc=1`, `smsSendFail=0` rather than trusting HTTP 200.

Delete one message using either an integer ID or a numeric string returned by `query_ids()`:

```python
router.sms.delete(42)
router.sms.delete("42")
```

Deletion requires the live-verified `resp=0`, `smsDelSucc=1`, `smsDelFail=0` success triple.

SMS bodies and phone numbers are personal data. The SDK does not add them to its own error details, and real SMS content/numbers should never be placed in public logs, fixtures or issue reports.

Draft-save and get-by-ID convenience helpers remain deferred until those complete request objects are normalized as stable public contracts.

## Physical-router integration tests

Normal tests are offline. The physical-router smoke suite is skipped unless the user explicitly sets:

```text
NR2301_INTEGRATION=1
```

and supplies the password through `NR2301_PASSWORD`.

Physical tests are split into explicit risk tiers: read-only, reversible-write and destructive/recovery. Ordinary CI enables none of them. The dedicated test router is used to expand coverage while sensitive output is sanitized and USB-management-mode mutation remains temporarily excluded as the active recovery channel.

See [`docs/integration-testing.md`](docs/integration-testing.md) for PowerShell, cmd.exe and Linux/macOS examples and the exact safety model.

## Design rules

The SDK follows the public API evidence instead of normalizing behavior that has not been proven:

- HTTP 200 is not treated as proof that a router operation succeeded.
- Numeric values are **not** globally converted to strings even though the stock frontend often does so. Per-method evidence wins; SMS send/delete emit their specifically verified stringified wire fields locally.
- Unknown response fields and unknown documented raw values are preserved.
- The base client does not invent undocumented success/error codes.
- High-level write helpers verify resulting state or endpoint-specific semantic success.
- Disruptive high-level helpers use read-back/recovery patterns where API research showed they are necessary.
- Engineering/supervisor credentials are not part of this SDK.
- Physical-router tests require explicit opt-in; normal CI must never contact a router.

## API baseline

The canonical protocol reference is external to this repository:

- API repository: <https://github.com/MarcLeinenDE/nr2301-api>
- immutable initial API release: `v0.1.0`
- current API development metadata used by the newest helpers: `0.1.1.dev0`
- tested firmware baseline: `V1.00(ACIY.3)C0`

The SDK does not maintain an independent hand-edited copy of the 157-method specification. New high-level helpers are promoted only after their contracts are normalized in the API repository.

## Maintainer / support expectations

This project grew out of a personal spare-time reverse-engineering project and is published so other users do not have to repeat the same work. Issues, corrections and pull requests are welcome. There is no commercial support or SLA. I have a young child and limited spare time, so replies and reviews may sometimes take a while.

## Security

Do not publish router passwords, Wi-Fi keys, VPN credentials, configuration backups, SMS contents, subscriber/SIM identifiers or live private network identifiers in issues or test fixtures. See [`SECURITY.md`](SECURITY.md).

## License

Software in this repository is licensed under **GPL-3.0-or-later**. See [`LICENSE`](LICENSE).

Copyright © 2026 Marc Leinen.
