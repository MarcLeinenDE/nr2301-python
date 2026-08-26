# nr2301-python

Unofficial Python SDK for the local management API of the **Zyxel NR2301** mobile router.

This SDK is built against the independently reverse-engineered API reference published in [`MarcLeinenDE/nr2301-api`](https://github.com/MarcLeinenDE/nr2301-api). The initial development baseline is API release [`v0.1.0`](https://github.com/MarcLeinenDE/nr2301-api/releases/tag/v0.1.0).

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or supported by Zyxel. The NR2301 API is undocumented by the manufacturer and may change between firmware versions.

## Status

`0.1.0.dev0` is the first SDK development baseline. It intentionally grows from the transport/authentication foundation into evidence-backed high-level helpers instead of pretending that all 157 documented API methods already have a stable Python wrapper.

Implemented so far:

- administrator challenge login (`account/get_rand` → MD5 challenge → `account/login`)
- `CGISID` session handling through `requests.Session`
- generic single-call API access
- generic multicall API access
- explicit transport/protocol/authentication/API exceptions
- context-manager support
- typed read-only `version` helpers
- typed mobile-network read helpers
- verified mobile-network writes for network mode and data roaming with exact read-back
- LAN/DHCP/DNS read helpers
- verified DNS write helpers using read → modify → multicall write → recovery → exact read-back
- typed Wi-Fi/WPS/extender read helpers
- evidence-backed Wi-Fi AP-section and WPS writes with recovery/read-back
- SMS mailbox summary/list/query helpers for the fully normalized public request contracts
- unit tests without requiring a physical router
- GitHub Actions test matrix for Python 3.10–3.13

Planned next:

- additional evidence-backed namespace helpers
- higher-level SMS writes after their full public request objects are normalized
- optional integration tests against a physical NR2301

## Install for development

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
pytest
```

## Quick start

Do not hard-code router passwords in source code. This example reads the password from an environment variable.

```python
import os

from nr2301 import NR2301Client

with NR2301Client(
    "http://192.168.1.1",
    username="admin",
    password=os.environ["NR2301_PASSWORD"],
) as router:
    router.login()

    print(router.version.info())
    print(router.mobile.cell_info())
    print(router.lan.dns())
    print(router.wifi.basic_info())
    print(router.sms.brief_info())
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

Multicall:

```python
results = router.multicall([
    {
        "path": "cm",
        "method": "get_cell_info",
        "data": {},
        "timeout": 2,
    }
])
```

## Mobile network

Read cellular/WAN state and current settings:

```python
print(router.mobile.cell_info())
print(router.mobile.wan_info())
print(router.mobile.network_settings())
```

The API reference deliberately does not define one universal hard-coded list of network-mode strings. Ask the target router which values it currently exposes:

```python
modes = router.mobile.available_network_modes().get("network_modes", [])
for mode in modes:
    print(mode)
```

After selecting one of those exact strings, pass it back to the high-level helper:

```python
selected_mode = input("Network mode: ")
verified = router.mobile.set_network_mode(selected_mode)
print(verified["network_mode"])
```

`set_network_mode()` refuses a value that is not present in the router's current available-mode list, writes only the `network_mode` field through `cm/set_network_settings`, and returns only after exact read-back confirms the requested value. A mode that is already active is returned without an unnecessary write.

Data roaming uses the same evidence-backed setter and verification pattern:

```python
router.mobile.set_data_roaming(True)
router.mobile.set_data_roaming(False)
```

The current public API contract does not fully reconstruct APN/profile writes through `cm/set_network_settings`, so this SDK does not invent such helpers.

## LAN / DHCP / DNS

Read the combined state or just the DNS subset:

```python
dhcp = router.lan.dhcp()
dns = router.lan.dns()
address = router.lan.address()
```

Set manual upstream DNS resolvers:

```python
verified = router.lan.set_dns(
    "1.1.1.1",
    "1.0.0.1",
    ipv6_primary="2606:4700:4700::1111",
    ipv6_secondary="2606:4700:4700::1001",
)
print(verified)
```

Return to automatic DNS:

```python
router.lan.set_dns_auto()
```

> [!WARNING]
> The NR2301 uses a combined LAN/DHCP/DNS setter that may reset management connectivity. The high-level DNS helper therefore copies the complete current DHCP object, changes only the DNS fields, writes it through multicall, then requires exact read-back. A lost HTTP response is treated as inconclusive rather than as proof of failure or success.

The configured manual addresses are upstream resolvers for the NR2301 DNS proxy. Clients may still receive the router's LAN address as their DNS server.

## Wi-Fi / WPS / extender

Read the complete AP configuration or individual status surfaces:

```python
print(router.wifi.config())
print(router.wifi.basic_info())
print(router.wifi.wps())
print(router.wifi.wps_status())
print(router.wifi.extender_status())
```

`update_ap_section()` first copies the current router-provided section, changes only the requested keys, writes the complete preserved section, then verifies those changed keys after recovery:

```python
router.wifi.update_ap_section(
    "wifi_if_24G",
    {"ssid": "Example-SSID"},
)
```

The same helper can update documented fields such as `key`, `channel`, `hidden`, `encryption` or Guest `maxassoc` without reconstructing the remainder of that AP block from defaults.

WPS enable/disable uses the live-verified string transport value and read-back:

```python
router.wifi.set_wps_enabled(True)
router.wifi.set_wps_enabled(False)
```

> [!WARNING]
> `wifi_set_ap_config` and `wifi_set_wps_disable` are disruptive operations. If the SDK itself is connected through the Wi-Fi network whose SSID or key is changed, the operating system may need to reconnect to that network before HTTP read-back can succeed. The SDK can recover HTTP sessions, but it cannot reconfigure the host operating system's Wi-Fi connection.

The SDK does not currently invent convenient Dual/Split/Guest mode aliases. Wi-Fi mode tokens remain firmware/API values until a stable public semantic contract exists.

## SMS

The SDK exposes the SMS requests whose public payload contracts are fully normalized:

```python
summary = router.sms.brief_info()
page = router.sms.list_by_type(0, page_index=1)
ids = router.sms.query_ids(message_type=4, read=2, location=0)
```

`list_type`, `message_type`, `read` and `location` remain endpoint-scoped raw values rather than being mapped to guessed cross-method enums. `query_ids()` uses the documented `sms.query` semantic success rule (`resp == 0`) and parses the returned comma-separated IDs into strings.

The public API reference confirms that `sms.send`, `sms.delete`, `sms.save` and `sms.get_by_id` exist and have been live exercised, but their complete frontend-shaped `sms` request objects are not yet normalized in `nr2301-api v0.1.0`. This SDK therefore does **not** invent high-level `send()`/`delete()` payloads yet. The generic `router.call()` remains available for users who deliberately work from their own verified request object.

SMS bodies and phone numbers are personal data. Do not place real SMS contents or numbers in public logs, fixtures or issue reports.

## Design rules

The SDK follows the public API evidence instead of normalizing behavior that has not been proven:

- HTTP 200 is not treated as proof that a router operation succeeded.
- Numeric values are **not** globally converted to strings even though the stock frontend often does so. Per-method evidence wins.
- Unknown response fields are preserved.
- The base client does not invent undocumented success/error codes.
- High-level write helpers verify the resulting state rather than trusting transport success alone.
- Disruptive high-level helpers use read-back/recovery patterns where the API research showed they are necessary.
- Engineering/supervisor credentials are not part of this SDK.

## API baseline

The canonical protocol reference is external to this repository:

- API repository: <https://github.com/MarcLeinenDE/nr2301-api>
- pinned initial API release: `v0.1.0`
- tested API firmware baseline: `V1.00(ACIY.3)C0`

The SDK should not maintain an independent hand-edited copy of the 157-method specification. Where practical, future CI/code generation should validate against the published API specification instead.

## Maintainer / support expectations

This project grew out of a personal spare-time reverse-engineering project and is published so other users do not have to repeat the same work. Issues, corrections and pull requests are welcome. There is no commercial support or SLA. I have a young child and limited spare time, so replies and reviews may sometimes take a while.

## Security

Do not publish router passwords, Wi-Fi keys, VPN credentials, configuration backups, SMS contents, subscriber/SIM identifiers or live private network identifiers in issues or test fixtures. See [`SECURITY.md`](SECURITY.md).

## License

Software in this repository is licensed under **GPL-3.0-or-later**. See [`LICENSE`](LICENSE).

Copyright © 2026 Marc Leinen.
