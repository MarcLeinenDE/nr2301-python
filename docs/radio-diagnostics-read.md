# Radio diagnostics read coverage

This SDK block exposes the two normal-admin radio diagnostic reads that the public API documents as multicall-only on the tested firmware.

## Scope

- `client.mobile.carrier_aggregation_info()` → `cm/get_ca_info`
- `client.mobile.radio_metrics()` → `cm/query_eng_info`
- transport: one-member `POST /api.cgi?multicalls=1`
- member shape: `{"path":"cm","method":"..."}` with no `data` field
- response handling: exactly one object in the multicall `responses` array

Both methods are upstream `LIVE_VERIFIED_LIMITED`, `ADMIN_MULTICALL_ONLY`, `READ_OR_LOW_SIDE_EFFECT`. Direct normal-admin path/method dispatch is authorization-denied; the SDK therefore does not attempt a direct-call fallback.

The helpers preserve the complete inner response object without inventing a stable CA/radio schema. In particular, an empty `ca_info`/`nr_ca_info` array must not be interpreted as proof that 5G is absent, and missing radio metrics are not synthesized.

No engineering-mode, band, operator-selection or mobile-network write is part of this block.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

The targeted read-only integration selection completed successfully:

```text
1 passed, 11 deselected in 0.77 s
```

The existing mobile status group exercised both new helpers in addition to the established mobile reads. The successful run confirms that the one-member multicall request shape and the SDK's single-object `responses` envelope parser match the physical ACIY.3 behavior.

The test did not print or assert concrete cell identifiers, bands, CA members or radio measurements. No write or connectivity transition occurred.

No `nr2301-api` change was required by this run because the multicall-only authorization behavior, one-member sufficiency and safety classification were already documented upstream; this adds public-SDK physical-path evidence only.