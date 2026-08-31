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

## Project target: complete SDK coverage

The long-term target is for this SDK to expose **all locally usable API functionality documented in `nr2301-api`**, not merely a small curated subset.

Complete coverage does not mean inventing wrappers for unknown contracts. For methods whose request/response semantics are incomplete, use the dedicated physical test router and upstream research to complete the API contract first, then implement the SDK surface.

A method may start as a close-to-wire namespace helper and later gain a more ergonomic high-level helper when semantics are sufficiently proven. The generic `client.call()` / `client.multicall()` APIs remain useful escape hatches, but they do not by themselves satisfy the long-term complete-SDK-coverage target.

### Mandatory API feedback loop

Physical SDK testing is also API research. When an SDK test reveals anything not already represented accurately upstream, update `nr2301-api` as part of the same work stream.

Examples:

- a previously `STATIC_CONFIRMED`/untested method succeeds live → promote the upstream verification status appropriately;
- a method is denied, rejected, unavailable or not implemented → record that upstream;
- a new request field, raw value, response field, success code, transport quirk or recovery behavior appears → normalize it upstream;
- an existing API assumption is disproved by the physical router → correct the API before treating the SDK implementation as final.

Do not leave new protocol truth only in tests, SDK comments or chat history.

## Current development state

The package is still on the `0.1.0.dev0` development line. Do not create or imply a stable SDK release without an explicit release decision and audit.

The SDK started from immutable API release `v0.1.0`; newer normalized contracts may track the API repository's current development state on `main`.

## Dedicated physical test router authority

The maintainer has explicitly designated the currently connected NR2301 as a **non-production test device**. It may be exercised over USB with read, write, disruptive and recovery tests in order to complete SDK/API coverage.

A physical factory-reset button is available as the final recovery path, and loss of the current test configuration is acceptable during planned testing.

This permission removes the old assumption that physical tests must remain read-only. It does **not** remove the need for deliberate test gates, state capture, read-back or restore evidence.

### Current hard exclusion: USB management mode

Do **not** mutate the router's USB/management mode, including engineering USB-mode setters, during routine coverage work. The USB path is the current control/recovery channel and should remain available.

Reading USB-mode state is acceptable when non-disruptive. Changing USB mode requires a separate future explicit plan; the general permission to test the router does not authorize it implicitly.

### Physical test levels and environment gates

Keep physical tests explicitly opt-in and separated by risk level:

```text
NR2301_INTEGRATION=1              read-only physical tests
NR2301_WRITE_INTEGRATION=1        reversible state-changing tests
NR2301_DESTRUCTIVE_INTEGRATION=1  disruptive/reset-capable tests
```

The read-only flag must never enable writes. The write flag must not silently enable factory-reset/destructive scenarios. A future test that performs a factory reset should use an additional test-specific confirmation/gate if needed.

CI must not set any physical-router integration flags.

For reversible writes, capture current state and restore it when practical. For disruptive tests, prepare the expected reconnect/re-authentication path. Factory reset is the final fallback, not the normal verification mechanism.

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

### Evidence-backed coverage, not fake coverage

The goal is broad/complete support, but each wrapper must reflect actual upstream evidence.

If a method cannot yet be wrapped safely because the contract is incomplete, treat that as an API research backlog item and use the dedicated test router to close the gap. Do not permanently omit useful methods merely to keep the SDK surface small.

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

Add further namespaces as coverage expands. Prefer names that describe proven behavior. Do not create attractive but unproven abstractions.

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
→ restore original state when practical
→ verify restore
```

Do not rebuild combined configuration objects from guessed defaults.

A lost HTTP response during a disruptive write is inconclusive. Read-back decides success when the protocol evidence supports that approach.

Same-state helpers should avoid unnecessary disruptive writes when practical.

## Known SDK pitfalls

### Authentication

The administrator challenge flow has historical live-working evidence. If a physical retest contradicts a current SDK/API assumption, preserve the raw endpoint-specific result and investigate rather than applying result-code meanings globally. Any corrected protocol finding must be fed back to `nr2301-api`.

### Wi-Fi

Verified modes currently include:

- `DUAL`
- `DUAL GUEST`
- `2.4G 5G`
- `2.4G 5G GUEST`

`set_separate_ssids()` must preserve the Guest token and current participating AP blocks.

`set_guest_enabled()` must preserve the current combined/split main mode and the current Guest configuration.

Independent Guest isolation remains incomplete on ACIY.3 because the getter does not safely round-trip that value; use physical research to close the gap before exposing a confident helper.

A Wi-Fi write may disconnect a Wi-Fi-connected machine. The current physical campaign uses USB as the management/recovery path, which makes Wi-Fi write verification suitable for the dedicated test router.

### DNS / combined DHCP setter

`client.lan.set_dns()` and `set_dns_auto()` must preserve the complete current combined DHCP object, change only DNS fields, use the documented multicall write and require read-back.

### Mobile network

`set_network_mode()` should validate against the mode values reported by the target router instead of relying on an SDK-owned universal enum.

### SMS

`send()` and `delete()` use endpoint-specific wire behavior normalized upstream. Do not move their stringification rules into the generic transport.

Normal SMS send must preserve the documented GSM7 detection, UTF-16BE uppercase-hex body encoding, address representation, timestamp format and SMS-specific success fields.

Physical SMS tests may use controlled real values locally, but do not include recipient numbers or message bodies in SDK-generated error messages, public logs, tests or fixtures.

### SIM

PIN/PUK mutation paths may now be deliberately researched on the dedicated non-production router when a specific test and recovery plan exists. Do not consume retries through broad/fuzz-style coverage. Feed every newly established result back into `nr2301-api` before promoting a stable helper.

### Client/MAC filtering

White-list mode can lock a Wi-Fi management client out. The USB-connected dedicated test device provides a better recovery channel, but helpers must still read current mode/state, verify the intended result and restore state when practical.

### USB mode

Treat USB-mode mutation as currently excluded. Do not add or run a physical setter test just to satisfy complete coverage while USB is the active control/recovery path.

## Testing

Normal development tests must work without a physical router.

Run:

```bash
pytest
```

The supported CI matrix is currently Python 3.10, 3.11, 3.12 and 3.13.

### Physical-router tests

Physical integration tests are hard opt-in through the risk-tier flags documented above. Credentials are supplied through environment variables, not source code.

Routine public test output should avoid collecting high-sensitivity data when unnecessary. Local targeted research may inspect such values, but committed/public evidence must sanitize SMS bodies, WLAN keys, IMSI/ICCID/IMEI, credentials and private MAC/IP inventories.

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

If a previously working feature appears absent or a physical retest contradicts the new SDK:

1. inspect the historical implementation/evidence;
2. compare the exact transport/request behavior;
3. check whether the old behavior was actually verified;
4. normalize/correct the protocol fact in `nr2301-api`;
5. implement or correct the SDK helper with tests;
6. run the physical test again and feed the result back upstream.

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

Local physical testing may necessarily observe some of these values. Sanitize them before copying logs or evidence into the repository.

## Documentation

When adding or changing a public helper:

- update tests;
- update `README.md` when the user-facing SDK surface changes materially;
- update `CHANGELOG.md` under `Unreleased`;
- mention important safety/recovery boundaries next to the affected feature;
- update `nr2301-api` first or in the same evidence cycle when the physical SDK test establishes new protocol truth.

Keep README examples safe to copy. Do not use real secrets or personal identifiers.

## Definition of done

An SDK/API coverage step is complete when:

1. its protocol contract and newest live verification state are represented upstream in `nr2301-api`;
2. endpoint-specific serialization/success logic stays out of the generic transport unless truly universal;
3. sensitive data is not embedded in public tests/logs/fixtures;
4. offline tests cover normal behavior and important failure/recovery cases;
5. the applicable physical test level has been run when needed;
6. state restore/recovery was verified when the scenario is reversible/disruptive;
7. Python 3.10–3.13 CI passes;
8. the package/wheel validation job passes;
9. README/CHANGELOG are updated when appropriate;
10. no new physical finding remains SDK-only or chat-only instead of being fed back into `nr2301-api`.
