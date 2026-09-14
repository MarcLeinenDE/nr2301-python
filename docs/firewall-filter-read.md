# Firewall filter read coverage

This SDK block exposes the two lower-level firewall filter-list reads using the NR2301 complete-list selector.

## Scope

- `client.firewall.ip_filter()` → `firewall/ww_read_ip_filter`
- `client.firewall.port_filter()` → `firewall/ww_read_port_filter`
- transport: direct authenticated POST
- request bodies:
  - `{"ww_ip_filter":{"list":["all"]}}`
  - `{"ww_port_filter":{"list":["all"]}}`
- response handling: preserve the complete `firewall` object and every list item raw

Both methods are upstream `LIVE_VERIFIED`, `ADMIN_OK`, `READ_OR_LOW_SIDE_EFFECT` reads.

## Why `list: ["all"]`

Historical NR2301 project artifacts from 2026-08-24 retained the frontend-derived full-list selector `list: ["all"]` for both endpoints. A later 2026-09-08 physical probe established that `list: []` is also accepted by both methods, but that result only proved a valid minimal request body; it did not prove that an empty list requests every configured rule.

The 2026-09-14 Firewall/NAT campaign therefore returned to the explicit `all` selector. A sanitized post-campaign residue check used the same authenticated API transport and reported:

```text
IP_FILTER_ALL_READ_COUNT = 0
IP_FILTER_NONEMPTY_COUNT_BEFORE = 0
IP_FILTER_SYNTHETIC_MATCH_COUNT = 0
IP_FILTER_CLEANUP = NOT_NEEDED
PORT_FILTER_ALL_READ_COUNT = 0
PORT_FILTER_NONEMPTY_COUNT_BEFORE = 0
PORT_FILTER_SYNTHETIC_MATCH_COUNT = 0
PORT_FILTER_CLEANUP = NOT_NEEDED
FIREWALL_FILTER_RESIDUE_CLEANUP = PASS
```

The router had no configured entries at that point. The SDK still keeps future non-empty rule items opaque rather than inventing a stable rule schema.

## Write scope remains separate

No filter-list write helper is exposed here. The 2026-09-14 research campaign physically confirmed the IP/port-filter enable/disable switches, but current non-empty `ww_edit_ip_filter` / `ww_edit_port_filter` payload hypotheses returned `setting_response='OK'` without producing a visible rule under a subsequent `list: ["all"]` read.

Those non-empty write contracts remain upstream research targets and are queued for targeted NR2301 WebUI capture rather than further guessed SDK behavior.

Protocol normalization and physical evidence are recorded in `nr2301-api` PR #9 / the 2026-09-14 Firewall/NAT evidence file.
