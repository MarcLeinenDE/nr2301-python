# Firewall/NAT targeted WebUI crawl

This runbook is for the quarantined NR2301 Firewall/NAT contracts that remained unresolved after the physical API campaign.

## Safety and evidence rules

- Work only on the dedicated test device.
- Observe the exact browser request produced by one UI action at a time; do not invent additional payload candidates during this crawl.
- Keep raw HAR/cURL exports local. This repository is public.
- Never commit cookies, authorization/session headers, passwords, CSRF/session tokens, real LAN/WAN addresses, MAC addresses, IMSI/IMEI data, or other device-specific secrets.
- Normalize only the HTTP method, CGI/API path, content type, request-body shape/field names, response semantics, and sanitized synthetic values required to reproduce the contract.
- Verify the resulting state through the normal SDK getter/read-back path after the UI action.
- Capture create/edit/delete or enable/disable flows separately when the UI exposes separate actions.

## Browser capture procedure

For each action below:

1. Open browser DevTools -> Network.
2. Enable `Preserve log` only if the WebUI reloads/navigation would otherwise lose the request.
3. Clear the Network log immediately before the action.
4. Prefer the Fetch/XHR filter, but also check `Doc`/`Other` if no request appears there.
5. Perform exactly one UI action.
6. Record the matching request's method, path, query parameters, content type, sanitized request body, and relevant response result.
7. Verify the resulting router state with the existing SDK getter or campaign read-back.
8. Restore the previous state in the WebUI where applicable, and capture the restore/delete request separately.

If using `Copy as cURL` or a HAR export for local analysis, remove at least `Cookie`, `Authorization`, CSRF/session-token headers and any private device/network identifiers before sharing or committing anything.

## Quarantine crawl order

### 1. Admin from WAN

- Record initial state with `client.firewall.admin_from_wan()`.
- Toggle the setting once in the WebUI.
- Capture the exact request and verify `admin_from_wan_enable` changed.
- Toggle back and capture the restore request separately.

Known failed API hypotheses: string `"0"/"1"` and native integer `0/1` using the current `set_admin_from_wan` candidate were rejected by the physical NR2301.

### 2. Ping from WAN

- Record initial state with `client.firewall.ping_from_wan()`.
- Toggle once in the WebUI.
- Capture and verify `ping_from_wan_enable` changed.
- Toggle back and capture the restore request separately.

Known failed API hypotheses: string `"0"/"1"` and native integer `0/1` using the current `set_ping_from_wan` candidate were rejected by the physical NR2301.

### 3. DMZ destination clear/delete

Current campaign state: DMZ is disabled, but a synthetic destination value may still be stored.

- Do not enable DMZ merely to clear the stored destination unless the WebUI itself requires that flow.
- Use the WebUI's native clear/delete/reset action for the destination if present.
- Capture that exact request.
- Verify with `client.firewall.dmz_info()` that the destination is empty/default according to the device's own semantics while `dmz_disable` remains disabled.

Do not perform further guessed DMZ-clear payloads.

### 4. IP filter rule add/delete

Use only the reserved documentation address `203.0.113.77` as the synthetic test address.

- Record current mode and item count.
- If required by the WebUI, enable the IP filter using the normal UI control.
- Create exactly one synthetic rule for `203.0.113.77` with the minimum fields the UI permits.
- Capture the add/save request and verify the rule is visible through the normal read-back path.
- Delete that exact synthetic rule in the WebUI.
- Capture the delete request separately and verify it is gone.
- Restore the original enable/disable state.

The previously tested cross-device 10-slot `"0"` sentinel list contract is not valid evidence for NR2301 rule creation: it was accepted at the transport layer but produced no rule on the physical device.

### 5. Port filter rule add/delete

Use `65500:65500` as the synthetic test port/range where the UI accepts that representation.

- Record current mode and item count.
- If required, enable the port filter through the WebUI.
- Create one synthetic rule using the minimum fields the UI requires.
- Capture the add/save request and verify read-back.
- Delete the synthetic rule and capture the delete request separately.
- Verify it is gone and restore the original enable/disable state.

Do not infer the NR2301 item schema from the rejected cross-device list candidate.

### 6. Port trigger add/delete

Use an unmistakable synthetic name such as `SDK-PT-WEBUI` and otherwise unused high ports such as `65500`/`65501` where the WebUI permits them.

- Record current enable state and item count with `client.firewall.port_trigger()`.
- Create exactly one test rule using the minimum fields accepted by the WebUI.
- Capture the create/save request and verify item count/content through read-back.
- Delete that exact rule in the WebUI and capture the delete request separately.
- Verify the original state/count is restored.

The item schema remains quarantined until this browser-produced contract is observed.

## Evidence to normalize after the crawl

For each capability, keep a compact sanitized record of:

- UI action and resulting state;
- HTTP method;
- endpoint/CGI path and relevant query keys;
- content type;
- request-body structure and exact field types;
- response/result semantics;
- SDK getter used for physical verification;
- restore/delete contract;
- whether the contract is now physically confirmed or remains quarantined.

Only after physical verification should a WebUI-observed contract be promoted into production SDK helpers/tests. The research PR should remain draft until the confirmed contracts are normalized and the exploratory harnesses are either removed or clearly retained as research evidence.