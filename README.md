# nr2301-python

Unofficial Python SDK for the local management API of the **Zyxel NR2301** mobile router.

This SDK is built against the independently reverse-engineered API reference published in [`MarcLeinenDE/nr2301-api`](https://github.com/MarcLeinenDE/nr2301-api). The initial development baseline is API release [`v0.1.0`](https://github.com/MarcLeinenDE/nr2301-api/releases/tag/v0.1.0).

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or supported by Zyxel. The NR2301 API is undocumented by the manufacturer and may change between firmware versions.

## Status

`0.1.0.dev0` is the first SDK development baseline. It intentionally starts with the transport/authentication foundation rather than pretending that all 157 documented API methods already have a stable high-level Python wrapper.

Implemented in this baseline:

- administrator challenge login (`account/get_rand` → MD5 challenge → `account/login`)
- `CGISID` session handling through `requests.Session`
- generic single-call API access
- generic multicall API access
- explicit transport/protocol/authentication exceptions
- context-manager support
- unit tests without requiring a physical router

Planned next:

- typed namespace helpers
- safe read/modify/write helpers for configuration blocks
- high-level mobile-network, LAN/DHCP/DNS, Wi-Fi and SMS workflows
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

    version = router.call("version", "get_ww_version")
    print(version)
```

A call with no `data` argument uses HTTP GET, matching the observed stock frontend behavior. Supplying `data` uses HTTP POST with JSON:

```python
result = router.call(
    "account",
    "get_retrytimes_and_time",
    data={"type": "admin"},
    authenticated=False,
)
```

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

## Design rules

The SDK follows the public API evidence instead of normalizing behavior that has not been proven:

- HTTP 200 is not treated as proof that a router operation succeeded.
- Numeric values are **not** globally converted to strings even though the stock frontend often does so. Per-method evidence wins.
- Unknown response fields are preserved.
- The base client does not invent undocumented success/error codes.
- Disruptive high-level helpers will use read-back/recovery patterns where the API research showed they are necessary.
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
