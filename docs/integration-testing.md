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
