# Changelog

## Unreleased

### Added

- added jurisdiction-neutral radio-capability policy and physical Wi-Fi write/restore coverage for the original WebUI 2.4/5-GHz net-mode and bandwidth enums; the SDK does not impose Germany/EU-specific radio limits
- clarified the SDK architecture as a complete router-capability layer: safety classifications control warnings/test gates/recovery requirements, while downstream apps/integrations decide which verified capabilities to expose; the older private app is evidence, not a feature-scope ceiling
- initial `0.1.0.dev0` SDK scaffold
- administrator challenge authentication
- generic single-call and multicall transport
- typed exception hierarchy
- context-manager lifecycle
- offline unit tests
- GitHub Actions test workflow
- typed read-only `version` helpers
- safe `client.device` reads for identity/platform metadata, runtime CPU/RAM/temperature, router/internet diagnostics, feature flags, interface MAC metadata, UI language, battery status and sleep-wait time
- safe `client.sim.status()` plus `client.sim.summary()` using the endpoint-scoped public SIM/PIN status semantics while preserving unknown raw values
- safe `client.statistics` reads for traffic counters, RX/TX transport activity, MAC-filter mode, optional login-client MAC metadata and the generic client inventory view
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
- explicitly opt-in physical-router integration tests guarded by `NR2301_INTEGRATION=1`; the initial smoke suite is read-only and deliberately avoids high-sensitivity identity/Wi-Fi-key/SMS-content reads
- staged physical-test policy for the dedicated non-production router: read-only, reversible-write and destructive/recovery levels, with USB-management-mode mutation explicitly excluded from the current campaign
- complete-SDK-coverage goal plus mandatory feedback of every new physical SDK finding into `nr2301-api`
- sanitized `examples/diagnose_auth_transport.py` probe that compares current requests transport with the historically working compact/header shape and an urllib reproduction without reading or transmitting the administrator password
- `tests/integration/test_reversible_writes.py`, hard-gated by `NR2301_WRITE_INTEGRATION=1`, covering data-roaming, available network-mode, WPS and Wi-Fi Guest/combined-vs-separate transitions with `try/finally` restoration and final exact read-back
- `tests/integration/test_lan_dns_write.py`, hard-gated by `NR2301_WRITE_INTEGRATION=1`, exercising the combined 12-field DHCP/DNS setter while asserting that all non-DNS fields remain unchanged and the complete original object is restored exactly

### Physical validation

- combined LAN/DHCP/DNS physical write test passed on 2026-08-31: DNS-only mutation preserved all seven non-DNS fields and the complete original 12-field object was restored exactly
- first full read-only physical SDK smoke completed successfully on 2026-08-31 against the USB-connected NR2301 using Python 3.13.5 and `http://zyxel.home`: all 8 integration groups passed in 4.01 s (version, device health, SIM, mobile, LAN/DNS, Wi-Fi, SMS summary and statistics)
- first reversible physical write suite completed successfully on 2026-08-31: all 4 tests passed in 51.09 s, covering data-roaming toggle/restore, one router-reported alternative network-mode change/restore, WPS toggle/restore, and Wi-Fi Guest plus combined/separate state-machine transitions with final original-state restoration

### Fixed / corrected

- hardened Wi-Fi write diagnostics so SSID/key/password-like fields are redacted from verification failures, and added a recovery/read-back helper for top-level Wi-Fi settings used by the physical capability campaign
- changed the default management URL from direct `http://192.168.1.1` to canonical `http://zyxel.home` after physical USB A/B testing proved administrator pre-auth is host/authority sensitive on firmware `V1.00(ACIY.3)C0`; both names resolve to the same IP, but the direct-IP path returns `result=4` while `zyxel.home` returns normal pre-auth success
- added a targeted authentication error hint when the tested direct management IP returns `result=4`, pointing callers to `http://zyxel.home`
- restored the historically live-working administrator login `user_id` shape to eight lowercase alphanumeric characters (`[a-z0-9]{8}`) instead of the initial SDK's invented 32-character hexadecimal value
- corrected the interim hypothesis that the 32-character user-id caused the physical `account/get_rand result=4`: the historical eight-character format also failed through the direct IP and then succeeded through `zyxel.home`, proving host/authority selection was the relevant difference in the controlled test
- restored the pre-login `account/get_retrytimes_and_time` guard so the SDK waits on an active lockout and refuses to consume the final remaining password attempt
- kept the 0..6 login result mapping scoped to `account/login`; `account/get_rand.result` is not interpreted through that table without endpoint-specific evidence

### Current research backlog

- run the hard-gated combined LAN/DHCP/DNS physical write test and feed any new transport/recovery evidence back into `nr2301-api`
- expand physical coverage into separately gated disruptive/recovery tests
- close incomplete API contracts and then expose the corresponding SDK methods until all locally usable API functionality is represented
- research SIM PIN/PUK mutation paths deliberately on the dedicated test router without broad retry-consuming probes
- `sim/get_lock_info` remains without a stable high-level JSON helper because the tested firmware returned HTTP 200 with an empty response body; revisit with targeted physical evidence
- normalize exact raw `statistics/get_conn_clients_info.request_type` tokens before adding semantic aliases
- normalize remaining SMS draft-save/get-by-ID contracts before adding convenience helpers
- close the ACIY.3 Guest-isolation getter/setter asymmetry before exposing an independent isolation helper
- keep USB-mode mutation out of physical coverage while USB is the active control/recovery channel

The SDK started from immutable `nr2301-api v0.1.0`; the newest normalized contracts track the API repository's `0.1.1.dev0` development state on `main`.
