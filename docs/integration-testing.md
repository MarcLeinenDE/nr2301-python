# Physical-router integration testing

The normal test suite is fully offline. It must never contact a router merely because somebody runs `pytest` or because GitHub Actions executes the test matrix.

Physical NR2301 tests are therefore **explicitly opt-in**.

## Dedicated test-device status

The current physical NR2301 has been explicitly designated by the maintainer as a **non-production test device**. It is connected to the test PC over USB and may be used for deliberate read, write, disruptive and recovery tests while the SDK/API coverage campaign is active.

Current assumptions:

- loss of the current router configuration is acceptable during planned testing;
- a physical factory-reset button is available as final recovery;
- USB is the preferred management/recovery channel during the campaign;
- **USB/management-mode mutation is currently excluded**, because changing it could remove the control/recovery channel itself.

This is broader permission than the initial read-only smoke phase, but physical testing remains gated so ordinary `pytest` and CI can never mutate a router accidentally.

## Canonical management host

On the tested firmware `V1.00(ACIY.3)C0`, `zyxel.home` resolves to the same management address as `192.168.1.1`, but administrator pre-auth calls are host/authority sensitive.

Physical USB A/B testing on 2026-08-31 showed:

```text
http://192.168.1.1
  account/get_retrytimes_and_time -> result=4
  account/get_rand                -> result=4

http://zyxel.home
  account/get_retrytimes_and_time -> result=0, retry_times=5, remain_time=0
  account/get_rand                -> result=0, rand=<8-byte challenge>
```

The result was independent of requests-vs-urllib transport, compact JSON/header reproduction, WebUI bootstrap and prior explicit WebUI logout. Use `http://zyxel.home` for administrator login on this firmware. Anonymous/status reads may still work through the direct IP and therefore do not prove that the direct IP is suitable for login.

## Test levels

### Level 1 — read-only

Opt-in:

```text
NR2301_INTEGRATION=1
```

The existing smoke suite uses this level. It does not mutate configuration.

It also deliberately avoids several sensitive read surfaces during routine smoke testing:

- `device.info()` — may contain IMEI, IMSI, ICCID and serial number
- `device.mac_info()` — contains device/network MAC addresses
- `wifi.config()` — contains SSIDs and Wi-Fi keys
- SMS mailbox listing — contains message bodies and phone numbers

The smoke suite reads only non-secret/status-oriented surfaces such as version, runtime health, internet diagnostics, battery state, SIM/PIN status, mobile-network status, LAN/DNS state, basic Wi-Fi/WPS status, SMS counts and traffic counters.

Physical USB result on 2026-08-31 using Python 3.13.5 and `http://zyxel.home`:

```text
8 passed in 4.01s
```

The passing groups were version, device health, SIM status, mobile status, LAN/DNS reads, Wi-Fi status, SMS summary and statistics reads.

### Level 2 — reversible writes

Opt-in reserved for dedicated state-changing tests:

```text
NR2301_WRITE_INTEGRATION=1
```

A Level-2 test should normally:

```text
read current state
→ preserve it
→ perform one evidenced change
→ read back and verify
→ restore the original state
→ read back and verify restore
```

The first Level-2 suite is `tests/integration/test_reversible_writes.py` and covers:

- mobile-data roaming toggle + restore;
- mobile network-mode change + restore when the router reports an alternative mode;
- WPS toggle + restore;
- Wi-Fi Guest and combined/separate state transitions + restore.

Each test uses `try/finally` so restoration is attempted even when an intermediate assertion or write verification fails. The Wi-Fi test deliberately uses the USB management path so Wi-Fi mode changes do not remove the test PC's management connection.

The read-only `NR2301_INTEGRATION=1` flag must never enable these tests.


### Extra gate for external SMS transmission

Physical tests that actually transmit an SMS to the mobile network require an additional explicit opt-in beyond the normal Level-2 write flag:

```text
NR2301_SMS_EXTERNAL_INTEGRATION=1
NR2301_SMS_TEST_NUMBER=<operator-controlled handset number>
```

The reusable E2E test is `tests/integration/test_sms_end_to_end_reply.py`. It requires both `NR2301_WRITE_INTEGRATION=1` and `NR2301_SMS_EXTERNAL_INTEGRATION=1`, so ordinary reversible-write testing cannot send an external SMS accidentally.

For the current maintainer test environment only, the integration test accepts a German national-format number such as `0176...` and converts it locally to `+49176...`. This is a test-harness convenience, **not** SDK number-normalization policy; `client.sms.send()` remains country-neutral and sends the recipient supplied by the caller.

The test never prints the phone number or SMS body. It correlates the newly created Outbox row primarily by new message ID plus normalized target address. Body content is only secondary evidence because a byte-exact full-body comparison proved unnecessarily brittle during the first real E2E run.

### Level 3 — disruptive / reset-capable

Opt-in reserved for operations that can interrupt management/service or deliberately lose state:

```text
NR2301_DESTRUCTIVE_INTEGRATION=1
```

Examples may eventually include reboot, connectivity-changing operations, factory-reset workflows or tests whose primary recovery is the physical reset button.

A destructive suite must document its expected recovery path and must not be enabled by either lower-level flag alone.

A factory-reset test may additionally use a test-specific confirmation flag so that even the destructive integration level cannot trigger it accidentally.

### Current hard exclusion — USB mode

Do **not** run setters that change the router's USB/management mode while USB is the active test/control channel. Reading the current USB mode is acceptable when non-disruptive.

This exclusion remains in force even when `NR2301_DESTRUCTIVE_INTEGRATION=1` is set, unless a future test plan explicitly replaces it.

## API/SDK synchronization requirement

A physical SDK test is also API research.

When a test changes what is known about a method, update `nr2301-api` in the same work stream:

- previously static/untested method succeeds → promote live verification status;
- method is denied/rejected/not applicable/not implemented → record the observed status;
- new request/response fields, result codes, raw values, transport quirks or recovery behavior appear → normalize them upstream;
- a previous API assumption is disproved → correct it upstream before considering the SDK work complete.

The final SDK target is complete coverage of the locally usable API, but incomplete protocol contracts must be researched rather than guessed.

## Credentials and environment

The administrator password must be supplied separately:

```text
NR2301_PASSWORD=<router admin password>
```

Optional variables:

```text
NR2301_URL=http://zyxel.home
NR2301_USERNAME=admin
```

`NR2301_URL` and `NR2301_USERNAME` use those values as defaults when omitted.

## PowerShell read-only example

```powershell
$env:NR2301_INTEGRATION = "1"
$env:NR2301_PASSWORD = "<password>"
$env:NR2301_URL = "http://zyxel.home"

python -m pytest tests/integration/test_readonly_router.py -v
```

## PowerShell reversible-write example

Run the read-only suite first. When it is green and the router is the designated test device:

```powershell
$env:NR2301_WRITE_INTEGRATION = "1"
$env:NR2301_PASSWORD = "<password>"
$env:NR2301_URL = "http://zyxel.home"

python -m pytest tests/integration/test_reversible_writes.py -v
```

The write suite restores original state in `finally` blocks. If a test still fails, inspect the full output before re-running it; do not repeatedly fire a failing state-changing test without understanding whether restoration completed.

Remove credentials/flags from the environment afterwards:

```powershell
Remove-Item Env:NR2301_PASSWORD
Remove-Item Env:NR2301_INTEGRATION -ErrorAction SilentlyContinue
Remove-Item Env:NR2301_WRITE_INTEGRATION -ErrorAction SilentlyContinue
Remove-Item Env:NR2301_DESTRUCTIVE_INTEGRATION -ErrorAction SilentlyContinue
```

## cmd.exe read-only example

```bat
set NR2301_INTEGRATION=1
set NR2301_PASSWORD=<password>
set NR2301_URL=http://zyxel.home
python -m pytest tests/integration/test_readonly_router.py -v
set NR2301_PASSWORD=
set NR2301_INTEGRATION=
```

## Linux/macOS read-only example

```bash
NR2301_INTEGRATION=1 \
NR2301_PASSWORD='<password>' \
NR2301_URL='http://zyxel.home' \
python -m pytest tests/integration/test_readonly_router.py -v
```

## Privacy of physical evidence

Local research may inspect real device/subscriber/network data when necessary to understand a method. Before committing logs, fixtures or documentation, sanitize:

- passwords and `CGISID`
- Wi-Fi keys
- VPN/DDNS credentials
- SMS bodies and phone numbers
- IMSI/ICCID/IMEI/serial values
- private MAC/IP identifiers
- configuration backups containing secrets

The goal is complete protocol evidence, not publication of the maintainer's real device data.

## CI behavior

GitHub Actions does not set any `NR2301_*_INTEGRATION` physical-test flag, so physical-router modules are skipped and no network attempt is made toward the default router host.

## Completed physical Wireless action coverage — 2026-08-31

The dedicated-router WPS action test passed end-to-end in `1.44 s`:

```text
PBC              -> wireless.wps_call_pbc_result = OK
Cancel after PBC -> top-level wps_call_cancel_result = OK
PIN 12345670     -> wireless.wps_call_pin_result = OK
Cancel after PIN -> top-level wps_call_cancel_result = OK
```

The original WPS-enable state was restored. Together with the preceding Wi-Fi configuration/security campaigns, the 14-method public `wireless` API namespace now has explicit SDK surface coverage and physical end-to-end evidence for its action wrappers.

## Completed physical SIM PIN lifecycle coverage — 2026-08-31

The guarded SIM campaign now physically verifies the normal locally usable PIN lifecycle without consuming retries or publishing credentials:

```text
initial                    pin_enabled=0  pin_status=5  retries=3/10
enable_pin                 setting_response=OK
change_pin original->temp  setting_response=OK
change_pin temp->original  setting_response=OK
disable_pin                setting_response=OK
reboot with PIN enabled    real management outage confirmed
post-reboot stable state   pin_enabled=1  pin_status=2  retries=3/10
provide_pin                setting_response=OK
post-provide read-back     pin_enabled=1  pin_status=5  retries=3/10
restore disable_pin        setting_response=OK
final                      pin_enabled=0  pin_status=5  retries=3/10
```

A key reboot-timing finding is that `router_call_reboot` may interrupt its own HTTP request several seconds before shutdown actually begins. Physical lifecycle tests therefore require an observed management outage before accepting a later login as recovery, and they wait for a stable SIM state before deciding whether a PIN submission is appropriate.

`reset_pin_using_puk` remains intentionally unexercised: obtaining PUK evidence would require a legitimately blocked SIM or deliberately exhausting PIN retries. The campaign does not manufacture that failure state merely for coverage.

## Completed physical SMS SDK exchange coverage — 2026-08-31

A real external exchange now verifies the complete public-SDK path without retaining message content or phone numbers in repository evidence:

```text
existing Inbox count                 1
client.sms.send()                    resp=0 / smsSendSucc=1 / smsSendFail=0
physical handset receipt             confirmed by operator
handset reply                        appeared as new router Inbox item
reply read flag before get_by_id     0
client.sms.get_by_id(reply_id)       success
observed response fields             address, body, contact_id, date, id,
                                     location, protocol, read, resp, status, type
Outbox list body representation      UTF-16BE hexadecimal
inbound get_by_id body representation UTF-16BE hexadecimal
```

The initial E2E test failed only at an overly strict Outbox full-body equality assertion despite successful physical delivery. A read-only recovery pass confirmed the expected synthetic message prefix and the real inbound reply. The reusable E2E test was therefore hardened to correlate primarily by newly appearing ID plus target address, with content prefix only as secondary disambiguation.

The inbound row was observed with `read=0` before `get_by_id`, but no second Inbox read was made afterwards. This campaign therefore does **not** claim that `get_by_id` actually changed the read state; the existing side-effect warning remains conservative.

## SMS Draft existing-ID semantics — 2026-08-31

The public SDK physically profiled `client.sms.save_draft(..., message_id=<existing Draft ID>)` on ACIY.3. The shipped frontend does send the current Draft ID when saving an edited Draft, but the tested firmware did not mutate that record in place:

```text
create Draft A                    success 0/1/0
get_by_id(original ID)            body class A
save Draft B with original ID     success 0/1/0
get_by_id(original ID)            still body class A
new Draft IDs                     exactly 1
get_by_id(new ID)                 body class B
behavior                          COPY_ON_SAVE
cleanup                           both synthetic IDs deleted
```

The Draft list and Draft `get_by_id` responses returned bare addresses (without the trailing comma used on the save wire), UTF-16BE-hex bodies and `type=2`. Tests log only representation/body classes and never recipient or body values.

The SDK keeps the `message_id` parameter because it is part of the source-backed capability contract, but callers must not assume that an existing ID means in-place update on every firmware.

