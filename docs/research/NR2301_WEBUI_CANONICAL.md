<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# NR2301 WebUI canonical research record

This is the sanitized, reusable WebUI map derived from the dedicated physical NR2301 test router on 2026-09-14.

Raw screenshots, rendered HTML, request logs and local device values are intentionally **not** committed. The private/raw evidence bundle had SHA-256 `09a7f72d942f6e0af2f49c9291072baa3b93fae65e30ac0f01e15ed59f60d942`. The normalized record below contains only routes, menu structure, source-derived protocol shapes and non-secret method names.

## Crawl quality

- Crawler generation: v6
- 39 discovered routes
- 36 browser-rendered routes
- 364 route/source links
- queue exhausted (`completed=true`)
- 4 blocked POST requests remain, all the same read-only dashboard multicall (`statistics/stat_get_common_data`, `router/get_runtime_info`, `statistics/get_conn_clients_info`); no Firewall/NAT page depends on these blocks
- `engineering.html` and `html/engineer_info.html` are deliberately source-only because their DOM repeatedly wedged Chromium
- `html/set_wan.html`, `html/set_qos.html` and `html/engineering.html` returned HTTP 404 from direct source fetch; they remain recorded because shipped frontend/static source references them

## Top-level navigation

1. `NETWORK STATUS` → `html/home.html`
2. `USER LIST` → `html/user.html`
3. `WI-FI SETTINGS` → `html/wireless.html`
4. `APP MODULE` → `html/module.html`

## APP MODULE

The shipped `module.html` groups routes as follows. Visibility is runtime/platform dependent; route presence in this record does not imply every tile is visible for every account/model state.

### Device Status

- Status → `html/set_status.html`
- Statistics → `html/set_connection.html`
- Network Information → `html/set_net_info.html`
- engineering/network-information variant → `html/engineer_info.html` (STC TOB conditional, source-only in crawler)

### Network Settings

- Network Settings → `html/set_network.html`
- Network Operators → `html/set_operators.html`
- DHCP → `html/set_dhcp.html`

### Device Management

- Package Settings → `html/set_traffic.html`
- Firewall → `html/firewall_ip.html`
- VPN → `html/set_vpn.html`
- Phonebook → `html/set_phonebook.html` (frontend condition excludes Zyxel profile)
- Messages → `html/set_smsinbox.html`
- PIN Settings → `html/set_pin.html`
- Admin Settings → `html/set_admin.html`
- Update → `html/set_update.html`
- Configuration Backup → `html/set_config.html`
- Device Reboot → `html/set_reboot.html`
- Diagnosis → `html/set_diagnosis.html`
- WPS → `html/set_wps.html`
- QoS → `html/set_qos.html` (`show:false`; direct source fetch 404)
- DDNS → `html/set_ddns.html`
- VPN Passthrough → `html/set_vpn_passthrough.html`
- Power Save → `html/set_power_save.html`
- Engineering → `engineering.html` for `accountType === 'super'`

## Firewall navigation

`APP MODULE → Firewall` resolves to `html/firewall_ip.html`. The firewall sidebar order is:

1. IP Filter → `html/firewall_ip.html`
2. URL Filter → `html/firewall_url.html`
3. Port Forward → `html/firewall_pf.html`
4. Port Trigger → `html/firewall_pt.html`
5. Port Filter → `html/firewall_port.html`
6. UPnP → `html/firewall_upnp.html`
7. Remote → `html/firewall_remote.html`
8. DMZ Settings → `html/firewall_dmz.html`

## Source-derived Firewall/NAT contracts

These shapes come from the **shipped NR2301 frontend source fetched from the physical device**, not from related-model guessing. They are static/source evidence unless a separate physical campaign already live-verified the same shape.

### Remote: WAN ping and administration

`firewall_remote.html` reads `get_ping_from_wan` and `get_admin_from_wan`.

The exact write bodies are:

```json
{"ping_from_wan": {"ping_from_wan_enable": "0"}}
```

or `"1"`, and:

```json
{"admin_from_wan": {"admin_from_wan_enable": "0"}}
```

or `"1"`.

The earlier rejected physical candidates omitted these nested wrapper objects. When the admin-from-WAN value changes, the frontend schedules `router/restart_web_server` after 600 ms.

### IP Filter

Full-list read is a multicall member:

```json
{"ww_ip_filter": {"list": ["all"]}}
```

Enable/disable:

```json
{"ww_ip_filter": {"ip_filter_disable": "0"}}
```

where `"0"` = enabled and `"1"` = disabled.

When enabled, the WebUI sends 10 indexed list entries:

```json
{
  "ww_ip_filter": {
    "list": [
      {"ip": "203.0.113.77", "index": 0},
      {"ip": "0", "index": 1}
    ]
  }
}
```

Empty UI slots are serialized as string `"0"`. This explains why earlier sparse/simple-list guesses did not define the actual UI contract.

### Port Filter

Full-list read:

```json
{"ww_port_filter": {"list": ["all"]}}
```

Enable/disable uses a **native integer**:

```json
{"ww_port_filter": {"port_filter_disable": 0}}
```

where `0` = enabled and `1` = disabled.

When enabled, the WebUI sends 10 indexed entries. A populated entry uses `"start:end"`; an empty/incomplete slot uses `"0"`:

```json
{
  "ww_port_filter": {
    "list": [
      {"port": "65500:65500", "index": 0},
      {"port": "0", "index": 1}
    ]
  }
}
```

### Port Trigger

Getter: `firewall/get_port_trigger`.

Disabled write:

```json
{"enable": 0}
```

Enabled write uses `toStringData:false` and 10 indexed item slots:

```json
{
  "enable": 1,
  "items": [
    {
      "index": 0,
      "name": "SDK-PT-WEBUI",
      "trigger_port": "65500",
      "start_port": "65501",
      "end_port": "65501"
    }
  ]
}
```

The frontend evaluates `result === 0` as success. Each populated row requires all four fields.

### Port Forward

Getter: `firewall/get_port_forward`.

Disabled write:

```json
{"enable": 0}
```

Enabled write uses `toStringData:false` and 10 indexed slots:

```json
{
  "enable": 1,
  "items": [
    {
      "index": 0,
      "name": "example",
      "mac": "02-00-00-00-00-01",
      "local_port": "65500",
      "wan_port": "65500"
    }
  ]
}
```

### URL Filter

Getter: `firewall/get_url_filter`.

Setter uses `toStringData:false`:

```json
{
  "mode": "blacklist",
  "black_items": [
    {"value": "example.invalid", "index": 0}
  ]
}
```

For whitelist mode the corresponding key is `white_items`; disabled mode is `"disable"`.

### UPnP

Getter: `firewall/ww_upnp_open_close_state`.

Setter:

```json
{"ww_upnp": {"upnp_enable": "1"}}
```

or `"0"`; these are string values.

### Remote DMZ

The page reads `fw_get_disable_info`, `fw_get_dmz_info`, and `router_get_lan_ip`.

DMZ enable state write:

```json
{"dmz_disable": "0"}
```

where `"0"` = enabled and `"1"` = disabled.

A changed destination uses:

```json
{"dmz_dest_ip": "192.0.2.10"}
```

with `firewall/fw_edit_dmz_entry`.

The current NR2301 frontend explicitly comments that `fw_add_dmz_entry` is not implemented on the cpe.5g path and always uses `fw_edit_dmz_entry`. It exposes **no empty-destination clear/delete operation**. Therefore the DMZ clear/delete contract remains unresolved; do not infer a delete method from related devices.

### VPN passthrough

The shipped page confirms the physically verified native-integer contract and `toStringData:false`:

```json
{"pptp": 1, "l2tp": 1, "ipsec": 1}
```

## Route inventory

| # | Route | Label / purpose | Group | Source HTTP | Capture |
|---:|---|---|---|---:|---|
| 1 | `html/home.html` | NETWORK STATUS | `top-nav` | 200 | browser |
| 2 | `html/user.html` | USER LIST | `top-nav` | 200 | browser |
| 3 | `html/wireless.html` | WI-FI SETTINGS | `top-nav` | 200 | browser |
| 4 | `html/module.html` | APP MODULE | `top-nav` | 200 | browser |
| 5 | `html/wizard.html` | Wizard | `auxiliary` | 200 | browser |
| 6 | `html/set_update.html` | Update | `app-module/device-management` | 200 | browser |
| 7 | `html/set_firmware.html` | Firmware update helper | `auxiliary` | 200 | browser |
| 8 | `html/set_smsinbox.html` | Messages | `app-module/device-management` | 200 | browser |
| 9 | `html/set_pin.html` | PIN Settings | `app-module/device-management` | 200 | browser |
| 10 | `html/set_admin.html` | Admin Settings | `app-module/device-management` | 200 | browser |
| 11 | `html/set_traffic.html` | Package Settings | `app-module/device-management` | 200 | browser |
| 12 | `html/set_wan.html` | WAN (missing/404 route) | `auxiliary` | 404 | browser |
| 13 | `html/set_connection.html` | Statistics | `app-module/device-status` | 200 | browser |
| 14 | `engineering.html` | Engineering | `app-module/device-management` | 200 | source-only-engineering-route |
| 15 | `html/set_status.html` | Status | `app-module/device-status` | 200 | browser |
| 16 | `html/set_net_info.html` | Network Information | `app-module/device-status` | 200 | browser |
| 17 | `html/engineer_info.html` | Engineering Network Information | `app-module/device-status` | 200 | source-only-engineering-route |
| 18 | `html/set_network.html` | Network Settings | `app-module/network-settings` | 200 | browser |
| 19 | `html/set_operators.html` | Network Operators | `app-module/network-settings` | 200 | browser |
| 20 | `html/set_dhcp.html` | DHCP | `app-module/network-settings` | 200 | browser |
| 21 | `html/firewall_ip.html` | Firewall / IP Filter | `firewall` | 200 | browser |
| 22 | `html/set_vpn.html` | VPN | `app-module/device-management` | 200 | browser |
| 23 | `html/set_phonebook.html` | Phonebook | `app-module/device-management` | 200 | browser |
| 24 | `html/set_config.html` | Configuration Backup | `app-module/device-management` | 200 | browser |
| 25 | `html/set_reboot.html` | Device Reboot | `app-module/device-management` | 200 | browser |
| 26 | `html/set_diagnosis.html` | Diagnosis | `app-module/device-management` | 200 | browser |
| 27 | `html/set_wps.html` | WPS | `app-module/device-management` | 200 | browser |
| 28 | `html/set_qos.html` | QoS (hidden/missing route) | `app-module/device-management` | 404 | browser |
| 29 | `html/set_ddns.html` | DDNS | `app-module/device-management` | 200 | browser |
| 30 | `html/set_vpn_passthrough.html` | VPN Passthrough | `app-module/device-management` | 200 | browser |
| 31 | `html/set_power_save.html` | Power Save | `app-module/device-management` | 200 | browser |
| 32 | `html/engineering.html` | Engineering (missing/404 route) | `app-module/device-management` | 404 | source-only-engineering-route |
| 33 | `html/firewall_url.html` | Firewall / URL Filter | `firewall` | 200 | browser |
| 34 | `html/firewall_pf.html` | Firewall / Port Forward | `firewall` | 200 | browser |
| 35 | `html/firewall_pt.html` | Firewall / Port Trigger | `firewall` | 200 | browser |
| 36 | `html/firewall_port.html` | Firewall / Port Filter | `firewall` | 200 | browser |
| 37 | `html/firewall_upnp.html` | Firewall / UPnP | `firewall` | 200 | browser |
| 38 | `html/firewall_remote.html` | Firewall / Remote | `firewall` | 200 | browser |
| 39 | `html/firewall_dmz.html` | Firewall / DMZ Settings | `firewall` | 200 | browser |

## Publication boundary

The raw evidence contains live device UI state and may contain local IP/MAC/device identifiers. Keep it local/private. Only this sanitized route/contract record is suitable for the public research branch.
