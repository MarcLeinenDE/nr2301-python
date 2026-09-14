<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# NR2301 WebUI canonical research record

Sanitized reusable WebUI map derived from the dedicated physical NR2301 on 2026-09-14. Raw screenshots, rendered HTML, request logs and local device values remain private. Raw evidence SHA-256: `09a7f72d942f6e0af2f49c9291072baa3b93fae65e30ac0f01e15ed59f60d942`.

## Crawl quality

- crawler generation: v6
- 39 routes discovered
- 36 browser-rendered routes
- 364 route/source links
- queue exhausted (`completed=true`)
- 4 residual blocked requests were read-only dashboard multicalls (`statistics/stat_get_common_data`, `router/get_runtime_info`, `statistics/get_conn_clients_info`), not Firewall/NAT traffic; the crawler was subsequently fixed to allow `stat_get_*`
- `engineering.html` and `html/engineer_info.html` are source-only because their DOM repeatedly wedged Chromium
- `html/set_wan.html`, `html/set_qos.html`, and `html/engineering.html` are referenced by shipped source but direct source fetch returned 404

## Important transport rule

The shipped common `ajaxHandler` defaults to `toStringData=true`. Its JSON serializer converts numeric values to strings unless a page explicitly passes `toStringData:false`.

Therefore source literals such as `index: 0` do **not** necessarily mean native JSON integers on the wire. In this record:

- IP-filter and port-filter calls use the default transport, so numeric indices and the port-filter disable flag are wire strings.
- Port Forward, Port Trigger, URL Filter, and VPN Passthrough explicitly use `toStringData:false`; their numeric fields remain native JSON integers.

## Top-level navigation

1. `NETWORK STATUS` → `html/home.html`
2. `USER LIST` → `html/user.html`
3. `WI-FI SETTINGS` → `html/wireless.html`
4. `APP MODULE` → `html/module.html`

## APP MODULE

### Device Status
- Status → `html/set_status.html`
- Statistics → `html/set_connection.html`
- Network Information → `html/set_net_info.html`
- conditional engineering information → `html/engineer_info.html`

### Network Settings
- Network Settings → `html/set_network.html`
- Network Operators → `html/set_operators.html`
- DHCP → `html/set_dhcp.html`

### Device Management
- Package Settings → `html/set_traffic.html`
- Firewall → `html/firewall_ip.html`
- VPN → `html/set_vpn.html`
- Phonebook → `html/set_phonebook.html`
- Messages → `html/set_smsinbox.html`
- PIN Settings → `html/set_pin.html`
- Admin Settings → `html/set_admin.html`
- Update → `html/set_update.html`
- Configuration Backup → `html/set_config.html`
- Device Reboot → `html/set_reboot.html`
- Diagnosis → `html/set_diagnosis.html`
- WPS → `html/set_wps.html`
- QoS → `html/set_qos.html` (`show:false`, source 404)
- DDNS → `html/set_ddns.html`
- VPN Passthrough → `html/set_vpn_passthrough.html`
- Power Save → `html/set_power_save.html`
- Engineering → `engineering.html` for `accountType === 'super'`

## Firewall navigation

`APP MODULE → Firewall` resolves to `html/firewall_ip.html`.

1. IP Filter → `html/firewall_ip.html`
2. URL Filter → `html/firewall_url.html`
3. Port Forward → `html/firewall_pf.html`
4. Port Trigger → `html/firewall_pt.html`
5. Port Filter → `html/firewall_port.html`
6. UPnP → `html/firewall_upnp.html`
7. Remote → `html/firewall_remote.html`
8. DMZ Settings → `html/firewall_dmz.html`

## Source-derived Firewall/NAT contracts

These shapes come from the shipped NR2301 frontend fetched from the physical device. They are source-confirmed unless a separate physical campaign already live-verified the same shape.

### Remote: WAN ping

Read: `firewall/get_ping_from_wan`.

Write:

```json
{"ping_from_wan":{"ping_from_wan_enable":"0"}}
```

or `"1"`. Success: `firewall.setting_response == "OK"`.

### Remote: WAN administration

Read: `firewall/get_admin_from_wan`.

Write:

```json
{"admin_from_wan":{"admin_from_wan_enable":"0"}}
```

or `"1"`. Success: `firewall.setting_response == "OK"`. If the value changes, the WebUI schedules `router/restart_web_server` after 600 ms.

The earlier rejected physical candidates were flat values and therefore did not use the real WebUI shape.

### IP Filter

Complete read:

```json
{"ww_ip_filter":{"list":["all"]}}
```

Enable/disable:

```json
{"ww_ip_filter":{"ip_filter_disable":"0"}}
```

`"0"` = enabled, `"1"` = disabled.

The UI writes 10 indexed slots. Because this call uses default `toStringData=true`, the **wire index is a string**:

```json
{
  "ww_ip_filter": {
    "list": [
      {"ip":"203.0.113.77","index":"0"},
      {"ip":"0","index":"1"}
    ]
  }
}
```

Empty slots are string `"0"`.

### Port Filter

Complete read:

```json
{"ww_port_filter":{"list":["all"]}}
```

Enable/disable source code uses numeric literals, but the default transport stringifies them. Actual wire shape:

```json
{"ww_port_filter":{"port_filter_disable":"0"}}
```

`"0"` = enabled, `"1"` = disabled.

The UI writes 10 indexed slots. Both `index` and the disable flag are strings on the wire:

```json
{
  "ww_port_filter": {
    "list": [
      {"port":"65500:65500","index":"0"},
      {"port":"0","index":"1"}
    ]
  }
}
```

Populated entries use `"start:end"`; empty/incomplete slots use `"0"`.

### Port Trigger

Getter: `firewall/get_port_trigger`.

Disabled:

```json
{"enable":0}
```

Enabled calls use `toStringData:false`, so `enable` and `index` are native integers:

```json
{
  "enable":1,
  "items":[
    {"index":0,"name":"SDK-PT-WEBUI","trigger_port":"65500","start_port":"65501","end_port":"65501"}
  ]
}
```

The page iterates up to 10 slots and evaluates `result === 0` as success. Populated rows require all four textual fields.

### Port Forward

Getter: `firewall/get_port_forward`.

Disabled:

```json
{"enable":0}
```

Enabled uses `toStringData:false`, so `enable`/`index` remain native integers:

```json
{
  "enable":1,
  "items":[
    {"index":0,"name":"example","mac":"02-00-00-00-00-01","local_port":"65500","wan_port":"65500"}
  ]
}
```

### URL Filter

Getter: `firewall/get_url_filter`.

Setter uses `toStringData:false`:

```json
{"mode":"blacklist","black_items":[{"value":"example.invalid","index":0}]}
```

Whitelist uses `white_items`; disabled mode is `"disable"`.

### UPnP

Getter: `firewall/ww_upnp_open_close_state`.

Setter:

```json
{"ww_upnp":{"upnp_enable":"1"}}
```

or `"0"`.

### DMZ

Reads: `fw_get_disable_info`, `fw_get_dmz_info`, `router_get_lan_ip`.

Enable state:

```json
{"dmz_disable":"0"}
```

`"0"` = enabled, `"1"` = disabled.

Destination edit:

```json
{"dmz_dest_ip":"192.0.2.10"}
```

The current NR2301 frontend comments that `fw_add_dmz_entry` is not implemented on the cpe.5g path and always uses `fw_edit_dmz_entry`. It exposes no empty-destination clear/delete action. DMZ clear/delete therefore remains unresolved.

### VPN passthrough

The shipped page uses `toStringData:false`, matching the already live-verified native-integer contract:

```json
{"pptp":1,"l2tp":1,"ipsec":1}
```

## Route inventory

| # | Route | Purpose | Source | Capture |
|---:|---|---|---:|---|
| 1 | `html/home.html` | NETWORK STATUS | 200 | browser |
| 2 | `html/user.html` | USER LIST | 200 | browser |
| 3 | `html/wireless.html` | WI-FI SETTINGS | 200 | browser |
| 4 | `html/module.html` | APP MODULE | 200 | browser |
| 5 | `html/wizard.html` | Wizard | 200 | browser |
| 6 | `html/set_update.html` | Update | 200 | browser |
| 7 | `html/set_firmware.html` | Firmware helper | 200 | browser |
| 8 | `html/set_smsinbox.html` | Messages | 200 | browser |
| 9 | `html/set_pin.html` | PIN Settings | 200 | browser |
| 10 | `html/set_admin.html` | Admin Settings | 200 | browser |
| 11 | `html/set_traffic.html` | Package Settings | 200 | browser |
| 12 | `html/set_wan.html` | WAN reference | 404 | browser |
| 13 | `html/set_connection.html` | Statistics | 200 | browser |
| 14 | `engineering.html` | Engineering | 200 | source-only |
| 15 | `html/set_status.html` | Status | 200 | browser |
| 16 | `html/set_net_info.html` | Network Information | 200 | browser |
| 17 | `html/engineer_info.html` | Engineering Network Information | 200 | source-only |
| 18 | `html/set_network.html` | Network Settings | 200 | browser |
| 19 | `html/set_operators.html` | Network Operators | 200 | browser |
| 20 | `html/set_dhcp.html` | DHCP | 200 | browser |
| 21 | `html/firewall_ip.html` | Firewall / IP Filter | 200 | browser |
| 22 | `html/set_vpn.html` | VPN | 200 | browser |
| 23 | `html/set_phonebook.html` | Phonebook | 200 | browser |
| 24 | `html/set_config.html` | Configuration Backup | 200 | browser |
| 25 | `html/set_reboot.html` | Device Reboot | 200 | browser |
| 26 | `html/set_diagnosis.html` | Diagnosis | 200 | browser |
| 27 | `html/set_wps.html` | WPS | 200 | browser |
| 28 | `html/set_qos.html` | QoS reference | 404 | browser |
| 29 | `html/set_ddns.html` | DDNS | 200 | browser |
| 30 | `html/set_vpn_passthrough.html` | VPN Passthrough | 200 | browser |
| 31 | `html/set_power_save.html` | Power Save | 200 | browser |
| 32 | `html/engineering.html` | Engineering reference | 404 | source-only |
| 33 | `html/firewall_url.html` | Firewall / URL Filter | 200 | browser |
| 34 | `html/firewall_pf.html` | Firewall / Port Forward | 200 | browser |
| 35 | `html/firewall_pt.html` | Firewall / Port Trigger | 200 | browser |
| 36 | `html/firewall_port.html` | Firewall / Port Filter | 200 | browser |
| 37 | `html/firewall_upnp.html` | Firewall / UPnP | 200 | browser |
| 38 | `html/firewall_remote.html` | Firewall / Remote | 200 | browser |
| 39 | `html/firewall_dmz.html` | Firewall / DMZ Settings | 200 | browser |

## Publication boundary

Raw evidence may contain live local device state and remains private. This sanitized structure/contract record is the public reusable baseline.
