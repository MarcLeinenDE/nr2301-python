<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# AGENTS.md

Guidance for AI coding agents and automated contributors working in this repository.

This file applies to the entire repository. If a future subdirectory contains a more specific `AGENTS.md`, follow the nearest applicable file for work in that subtree.

## Project role

`nr2301-python` is the reusable Python SDK for the Zyxel NR2301 local management API.

Upstream protocol truth lives in:

- <https://github.com/MarcLeinenDE/nr2301-api>

Architecture:

```text
nr2301-api        protocol evidence and public contract
    ↓
nr2301-python     reusable SDK
    ↓
consumer apps / integrations / tools
```

Do not invent new protocol facts in this repository. If a helper requires a new request shape, raw value, enum, semantic rule or safety interpretation, normalize that fact in `nr2301-api` first.

## Current development state

The package is still on the `0.1.0.dev0` development line. Do not create or imply a stable SDK release without an explicit release decision and audit.

The SDK started from immutable API release `v0.1.0`; newer normalized contracts may track the API repository's current development state on `main`.

## Design principles

### Keep the generic transport generic

Do not put endpoint-specific quirks into `HTTPTransport` unless they are genuinely universal.

In particular:

- do **not** globally stringify numeric values;
- do **not** globally interpret `result`, `resp` or other method-specific fields;
- do **not** discard unknown response fields;
- do **not** hide transport/protocol failures behind guessed success semantics.

Endpoint-specific serialization and success rules belong in the relevant namespace helper.

### HTTP 200 is not enough

The router often returns HTTP 200 for outcomes that still need method-level interpretation. High-level helpers must use the documented endpoint-specific success criteria or read-back verification.

### Prefer evidence-backed helpers over broad fake coverage

A high-level wrapper is appropriate only when its contract is sufficiently normalized upstream.

The generic `client.call()` / `client.multicall()` APIs remain available for advanced use. Do not create a misleading convenience wrapper solely to claim support for more of the 157 documented methods.

## Namespace conventions

High-level features live under `src/nr2301/namespaces/` and are exposed as namespaces on `NR2301Client`, for example:

- `client.version`
- `client.device`
- `client.mobile`
- `client.sim`
- `client.lan`
- `client.wifi`
- `client.sms`
- `client.statistics`

Prefer names that describe proven behavior. Do not create attractive but unproven abstractions.

Examples:

- use combined/shared SSID wording for Wi-Fi `DUAL`; do not call it Band Steering unless separately proven;
- do not invent universal mobile-network mode aliases when the target router can report its actual mode values;
- do not invent `statistics` request-type aliases until their raw tokens are normalized upstream.

## Write-helper pattern

For state-changing methods, follow the strongest applicable upstream evidence.

A common safe pattern is:

```text
read current state
→ preserve unrelated fields
→ make the smallest evidenced change
→ write
→ tolerate documented management interruption
→ recover/re-authenticate when possible
→ read back
→ require exact intended state
```

Do not rebuild combined configuration objects from guessed defaults.

A lost HTTP response during a disruptive write is inconclusive. Read-back decides success when the protocol evidence supports that approach.

Same-state helpers should avoid unnecessary disruptive writes when practical.

## Known SDK pitfalls

### Wi-Fi

Verified modes currently include:

- `DUAL`
- `DUAL GUEST`
- `2.4G 5G`
- `2.4G 5G GUEST`

`set_separate_ssids()` must preserve the Guest token and current participating AP blocks.

`set_guest_enabled()` must preserve the current combined/split main mode and the current Guest configuration.

Do not expose an independent Guest-isolation helper on ACIY.3 because that value is not safely round-trippable in the public contract.

A Wi-Fi write may disconnect the machine running the SDK. The SDK can recover HTTP/session state but cannot reconfigure the host operating system's Wi-Fi connection.

### DNS / combined DHCP setter

`client.lan.set_dns()` and `set_dns_auto()` must preserve the complete current combined DHCP object, change only DNS fields, use the documented multicall write and require read-back.

### Mobile network

`set_network_mode()` should validate against the mode values reported by the target router instead of relying on an SDK-owned universal enum.

### SMS

`send()` and `delete()` use endpoint-specific wire behavior normalized upstream. Do not move their stringification rules into the generic transport.

Normal SMS send must preserve the documented GSM7 detection, UTF-16BE uppercase-hex body encoding, address representation, timestamp format and SMS-specific success fields.

Do not include recipient numbers or message bodies in SDK-generated error messages, logs, public tests or fixtures.

### SIM

Keep PIN/PUK mutation paths out of normal SDK coverage while upstream classifies them as static-only / `DO_NOT_TEST_FOR_COVERAGE`.

`sim/get_lock_info` must not be wrapped as a stable high-level JSON helper while the tested firmware returns an empty response body.

### Client/MAC filtering

White-list mode can lock a Wi-Fi management client out. Do not add high-level filter-mode write automation without explicit recovery prerequisites and the upstream safe workflow.

## Testing

Normal development tests must work without a physical router.

Run:

```bash
pytest
```

The supported CI matrix is currently Python 3.10, 3.11, 3.12 and 3.13.

### Physical-router tests

Physical integration tests are hard opt-in.

Current read-only opt-in:

```text
NR2301_INTEGRATION=1
```

with credentials supplied through environment variables, not source code.

The read-only integration flag must **never** enable writes.

Any future physical write suite must use a separate, explicit opt-in and must document recovery prerequisites. Do not merge read-only and write-level integration gates.

Routine integration smoke should avoid collecting high-sensitivity data when it is unnecessary, including SMS bodies, WLAN keys, IMSI/ICCID/IMEI and full private MAC inventories.

## Packaging gate

The GitHub Actions workflow validates both source tests and package installation.

A change is not complete if only editable-source tests pass but the built wheel fails.

The package job must continue to verify at least:

- wheel/sdist build succeeds;
- package metadata is correct;
- `py.typed` is packaged;
- license is packaged;
- the built wheel installs into a clean virtual environment;
- importing the installed package succeeds.

## Historical application parity

An earlier private NR2301 application may contain proven working behavior that an initial public SDK revision missed.

If a previously working feature appears absent:

1. inspect the historical implementation/evidence;
2. check whether the protocol behavior was actually verified;
3. normalize any missing protocol fact in `nr2301-api` first;
4. then implement the SDK helper with tests.

Do not treat historical application code as automatic protocol truth, but do not ignore it as an evidence source either.

## Privacy and secrets

Never commit or print real private values such as:

- administrator passwords
- `CGISID` session cookies
- Wi-Fi keys
- VPN/DDNS credentials
- SMS bodies or real phone numbers
- configuration backups containing secrets
- IMSI/ICCID/IMEI/serial values from private devices
- real private MAC/IP identifiers from a maintainer environment

Use synthetic fixtures and documentation-reserved addresses.

## Documentation

When adding or changing a public helper:

- update tests;
- update `README.md` when the user-facing SDK surface changes materially;
- update `CHANGELOG.md` under `Unreleased`;
- mention important safety/recovery boundaries next to the affected feature.

Keep README examples safe to copy. Do not use real secrets or personal identifiers.

## Definition of done

A high-level SDK change is complete when:

1. its protocol contract exists upstream in `nr2301-api`;
2. endpoint-specific serialization/success logic stays out of the generic transport unless truly universal;
3. sensitive data is not logged or embedded in tests;
4. offline tests cover normal behavior and important failure/recovery cases;
5. Python 3.10–3.13 CI passes;
6. the package/wheel validation job passes;
7. README/CHANGELOG are updated when appropriate;
8. physical-router testing remains opt-in and safety boundaries are preserved.
