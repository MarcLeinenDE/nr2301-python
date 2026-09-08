# Firewall / NAT read coverage

The first high-level firewall surface in `nr2301-python` is deliberately read-only.
It wraps only upstream methods that are already `LIVE_VERIFIED`, `ADMIN_OK` and
classified `READ_OR_LOW_SIDE_EFFECT` in `nr2301-api`.

## Exposed reads

`client.firewall` currently exposes:

- `disable_info()` → `firewall/fw_get_disable_info`
- `dmz_info()` → `firewall/fw_get_dmz_info`
- `vpn_passthrough()` → `firewall/fw_get_vpn_passthrough`
- `admin_from_wan()` → `firewall/get_admin_from_wan`
- `ping_from_wan()` → `firewall/get_ping_from_wan`
- `port_forward()` → `firewall/get_port_forward`
- `port_trigger()` → `firewall/get_port_trigger`
- `url_filter()` → `firewall/get_url_filter`
- `ip_filter_mode_state()` → `firewall/ww_read_switch_mode_state`
- `port_filter_mode_state()` → `firewall/ww_read_switch_port_mode_state`
- `upnp_state()` → `firewall/ww_upnp_open_close_state`

The SDK preserves raw firmware values and unknown fields rather than guessing or
normalizing configuration semantics. This is intentional for fields such as DMZ
state/address data, where historical firmware observations can look partial or
otherwise unusual.

## Physical validation — 2026-09-08

Tested against firmware `V1.00(ACIY.3)C0` through the public SDK and normal
administrator authentication.

Targeted command selected only `test_firewall_reads` from the read-only physical
integration suite.

Result:

```text
1 passed, 9 deselected in 1.05s
```

All eleven high-level firewall/NAT read helpers returned mapping responses through
the real router path.

The physical smoke intentionally did **not** print concrete configuration data.
Firewall/NAT responses may contain private IP addresses, port-forwarding/trigger
rules, URL-filter entries and other local operational configuration.

## Explicitly excluded

This block does not expose or physically exercise firewall/NAT writes, including:

- DMZ changes
- WAN administration enable/disable
- WAN ping enable/disable
- port-forwarding or port-trigger changes
- URL/IP/port-filter changes
- UPnP enable/disable

Those write paths require their own evidence-backed, recovery-aware SDK design and
are not implied by this read-only namespace.
