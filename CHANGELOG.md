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

The SDK is based on `nr2301-api v0.1.0`.
