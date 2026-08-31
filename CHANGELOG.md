# Changelog

## Unreleased

- added `client.sms.get_by_id()` and `client.sms.save_draft()` from normalized public contracts; draft create/update preserves the historically live-verified wire distinction (string id/type/protocol, boolean gsm7), enforces the save success triple, and redacts message content from SDK-generated errors
### Added

- added `client.sim.provide_pin()`, `enable_pin()`, `disable_pin()`, `change_pin()` and `reset_pin_using_puk()` using the exact normalized frontend payloads; helpers never log secrets and apply a default retry-budget guard that preserves the final PIN/PUK attempt while remaining explicitly overridable for deliberate recovery use
- added explicit `client.wifi.call_wps_pbc()`, `call_wps_pin()` and `call_wps_cancel()` wrappers for the already live-verified WPS action contracts, plus a reversible physical integration test that immediately cancels PBC/PIN and restores the original WPS-enable state
- added `client.wifi.set_security()` with all 13 physically verified encryption tokens on 24G/5G/DUAL/Guest; protected modes verify token+key, while open mode correctly verifies only `encryption=none` because ACIY.3 can retain a non-empty key field on 24G/5G/DUAL
- enhanced `examples/explore_wifi_security_matrix.py` with per-case checkpoint reports and `NR2301_SECURITY_START=SECTION:TOKEN` resume support so completed physical cases are not repeated after an interruption
- added `examples/explore_wifi_security_matrix.py`, a hard-gated sanitized 13-token × 4-section Wi-Fi security explorer that classifies accepted/coerced/unverified results, uses only synthetic keys, restores every AP block and writes a shareable credential-free JSON report while tracking the raw `password_modified` marker
- added `tests/integration/test_wifi_extended_writes.py` for the next capability round: exploratory top-level `power_level` candidates, global/Guest max-client lower-bound probes, Guest band selection, synthetic SSID writes, runtime-advertised upper/DFS channel paths, exhaustive original-WebUI net-mode/bandwidth tokens, and sanitized authenticated Wi-Fi scan verification
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

- SIM `provide_pin` lifecycle test passed on 2026-08-31 in 76.02 s: after enabling PIN protection, a real reboot outage was confirmed, administrator login recovered on attempt 27, the SIM stabilized at `pin_status=2`, one known-correct local PIN returned `response.setting_response=OK`, read-back returned to `pin_status=5`, retry counters remained 3/10, and PIN protection was restored to disabled
- WPS action integration passed on 2026-08-31 in 1.44 s: PBC returned nested `wireless.wps_call_pbc_result=OK`, Cancel returned flat top-level `wps_call_cancel_result=OK`, PIN `12345670` returned nested `wireless.wps_call_pin_result=OK`, the second Cancel was again flat/OK, and the original WPS-enable state was restored
- complete Wi-Fi security matrix finished on 2026-08-31: 52/52 section/token combinations accepted; every protected mode round-tripped the synthetic key on all four AP sections, open mode exposed section-specific key-field behavior, and `password_modified` remained 0 throughout
- extended Wi-Fi capability suite passed on 2026-08-31: all 18 cases passed in 226.96 s, confirming raw `power_level` values 0/1/2, global and Guest maxassoc=1, Guest 2.4G/5G band mode, synthetic SSID writes on all four AP blocks, 2.4-GHz channel 13, 5-GHz channels 52/100/140 including DFS-class paths, every source-known WebUI net-mode/bandwidth token, and normal-admin `wifi_scan`, with original state restored after every mutation
- comprehensive Wi-Fi field suite passed on 2026-08-31: all 15 cases passed in 178.96 s, covering representative 2.4/5-GHz fixed channels, Hidden on 24G/5G/DUAL/Guest, AP isolation on both bands, global maxassoc, timed-off persistence, master Wi-Fi switch, per-band net-mode and bandwidth changes, with exact read-back and final original-state restoration
- combined LAN/DHCP/DNS physical write test passed on 2026-08-31: DNS-only mutation preserved all seven non-DNS fields and the complete original 12-field object was restored exactly
- first full read-only physical SDK smoke completed successfully on 2026-08-31 against the USB-connected NR2301 using Python 3.13.5 and `http://zyxel.home`: all 8 integration groups passed in 4.01 s (version, device health, SIM, mobile, LAN/DNS, Wi-Fi, SMS summary and statistics)
- first reversible physical write suite completed successfully on 2026-08-31: all 4 tests passed in 51.09 s, covering data-roaming toggle/restore, one router-reported alternative network-mode change/restore, WPS toggle/restore, and Wi-Fi Guest plus combined/separate state-machine transitions with final original-state restoration

### Fixed / corrected

- fixed WPS action response handling after physical ACIY.3 evidence showed action-specific response envelopes: PBC/PIN return their `OK` results under `wireless`, while Cancel returns flat top-level `wps_call_cancel_result=OK`; helpers accept either physically evidenced envelope while still requiring the exact action result
- corrected Wi-Fi restore semantics after physical security-matrix evidence showed `cur_channel` can legitimately differ after restoring configured auto-channel state; physical restore helpers now compare only mutable configuration and exclude runtime/capability metadata (`cur_channel`, `first_channel`, `last_channel`, `channel_list`)
- hardened physical Wi-Fi restore assertions so a failed restore reports only mismatching field names instead of allowing pytest to render complete AP dictionaries containing real SSIDs/keys
- hardened Wi-Fi write diagnostics so SSID/key/password-like fields are redacted from verification failures, and added a recovery/read-back helper for top-level Wi-Fi settings used by the physical capability campaign
- changed the default management URL from direct `http://192.168.1.1` to canonical `http://zyxel.home` after physical USB A/B testing proved administrator pre-auth is host/authority sensitive on firmware `V1.00(ACIY.3)C0`; both names resolve to the same IP, but the direct-IP path returns `result=4` while `zyxel.home` returns normal pre-auth success
- added a targeted authentication error hint when the tested direct management IP returns `result=4`, pointing callers to `http://zyxel.home`
- restored the historically live-working administrator login `user_id` shape to eight lowercase alphanumeric characters (`[a-z0-9]{8}`) instead of the initial SDK's invented 32-character hexadecimal value
- corrected the interim hypothesis that the 32-character user-id caused the physical `account/get_rand result=4`: the historical eight-character format also failed through the direct IP and then succeeded through `zyxel.home`, proving host/authority selection was the relevant difference in the controlled test
- restored the pre-login `account/get_retrytimes_and_time` guard so the SDK waits on an active lockout and refuses to consume the final remaining password attempt
- kept the 0..6 login result mapping scoped to `account/login`; `account/get_rand.result` is not interpreted through that table without endpoint-specific evidence

### Current research backlog

- determine the exact meaning of the raw `password_modified` field; the complete 52-case security campaign proved it is not a generic Wi-Fi credential-change latch
- expand physical coverage into separately gated disruptive/recovery tests
- close incomplete API contracts and then expose the corresponding SDK methods until all locally usable API functionality is represented
- SIM `enable_pin`, `disable_pin`, `change_pin` and `provide_pin` are physically verified with known local credentials and unchanged retry budgets; keep `reset_pin_using_puk` recovery-only rather than manufacturing a blocked SIM merely for coverage
- `sim/get_lock_info` remains without a stable high-level JSON helper because the tested firmware returned HTTP 200 with an empty response body; revisit with targeted physical evidence
- normalize exact raw `statistics/get_conn_clients_info.request_type` tokens before adding semantic aliases
- normalize remaining SMS draft-save/get-by-ID contracts before adding convenience helpers
- close the ACIY.3 Guest-isolation getter/setter asymmetry before exposing an independent isolation helper
- keep USB-mode mutation out of physical coverage while USB is the active control/recovery channel

The SDK started from immutable `nr2301-api v0.1.0`; the newest normalized contracts track the API repository's `0.1.1.dev0` development state on `main`.
