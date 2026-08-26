# Changelog

## Unreleased

### Added

- initial `0.1.0.dev0` SDK scaffold
- administrator challenge authentication
- generic single-call and multicall transport
- typed exception hierarchy
- context-manager lifecycle
- offline unit tests
- GitHub Actions test workflow
- typed read-only `version` helpers
- typed mobile-network read helpers
- `client.mobile.set_network_mode()` with runtime available-mode validation and exact read-back verification
- `client.mobile.set_data_roaming()` with exact read-back verification
- LAN/DHCP/DNS read helpers
- `client.lan.set_dns()` and `client.lan.set_dns_auto()` with full-object preservation, disruptive-write recovery and exact DNS read-back verification
- typed Wi-Fi/WPS/extender read helpers
- `client.wifi.update_ap_section()` with router-state preservation, disruptive recovery and changed-field read-back verification
- `client.wifi.set_wps_enabled()` with exact `wps_enable` read-back verification
- `client.wifi.guest_enabled()` and `client.wifi.uses_separate_ssids()` for the verified Wi-Fi mode states
- `client.wifi.set_separate_ssids()` using the live-verified `DUAL` ↔ `2.4G 5G` state machine while preserving the Guest token and current AP blocks
- `client.wifi.set_guest_enabled()` using the verified `GUEST` mode token with Guest configuration preservation and disruptive recovery/read-back
- SMS mailbox summary/list/query helpers
- `client.sms.send()` using the normalized normal-SMS GSM7/UTF-16BE/timestamp wire contract and verified SMS-specific success fields
- `client.sms.delete()` using the normalized single-ID request and verified deletion success fields

### Deliberately deferred

- SMS draft-save and get-by-ID convenience helpers remain deferred until those full request objects are normalized as stable public contracts
- independent Guest isolation is not exposed on ACIY.3 because the getter does not safely round-trip that value

The SDK started from immutable `nr2301-api v0.1.0`; the newest Wi-Fi mode/Guest and SMS send/delete helpers track the API repository's normalized `0.1.1.dev0` development contracts on `main`.
