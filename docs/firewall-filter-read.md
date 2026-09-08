# Firewall filter read coverage

This SDK block exposes the two lower-level firewall filter-list reads whose minimal normal-admin request bodies were physically confirmed on ACIY.3.

## Scope

- `client.firewall.ip_filter()` → `firewall/ww_read_ip_filter`
- `client.firewall.port_filter()` → `firewall/ww_read_port_filter`
- transport: direct authenticated POST
- request bodies:
  - `{"ww_ip_filter":{"list":[]}}`
  - `{"ww_port_filter":{"list":[]}}`
- response handling: preserve the complete `firewall` object and every list item raw

Both methods are upstream `LIVE_VERIFIED`, `ADMIN_OK`, `READ_OR_LOW_SIDE_EFFECT`.

The tested ACIY.3 router accepted the empty-list bodies for both reads and returned `firewall.list` as a JSON list plus `firewall.setting_response` as a string. At the time of the probe both lists were empty. That observation does **not** define a schema for non-empty rule entries; the SDK therefore keeps rule items as opaque values rather than inventing IP/port filter fields.

No rule edit, mode change, firewall toggle or other write is part of this helper block.

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, tested firmware family ACIY.3, Python 3.13.5.

A preliminary sanitized direct-call probe established the minimal empty-list request bodies and response structure without printing any rule contents.

The subsequent public-SDK targeted read-only smoke completed successfully:

```text
1 passed, 11 deselected in 1.82 s
```

`test_firewall_reads` exercised both `client.firewall.ip_filter()` and `client.firewall.port_filter()` together with the existing read-only firewall surface. No IP addresses, ports or rule contents were printed and no firewall state was modified.

The corresponding protocol evidence is recorded upstream in `nr2301-api` PR #3.