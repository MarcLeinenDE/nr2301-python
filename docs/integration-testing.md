# Physical-router integration testing

The normal test suite is fully offline. It must never contact a router merely because somebody runs `pytest` or because GitHub Actions executes the test matrix.

Physical NR2301 tests are therefore **explicitly opt-in**.

## Safety model

The initial physical-router smoke suite is read-only.

It does not call configuration setters, reboot/reset actions, SMS send/delete, PIN/PUK operations, traffic-counter reset or MAC-filter writes.

It also deliberately avoids several sensitive read surfaces during routine smoke testing:

- `device.info()` — may contain IMEI, IMSI, ICCID and serial number
- `device.mac_info()` — contains device/network MAC addresses
- `wifi.config()` — contains SSIDs and Wi-Fi keys
- SMS mailbox listing — contains message bodies and phone numbers

The smoke suite reads only non-secret/status-oriented surfaces such as version, runtime health, internet diagnostics, battery state, SIM/PIN status, mobile-network status, LAN/DNS state, basic Wi-Fi/WPS status, SMS counts and traffic counters.

## Required opt-in

The integration module is skipped at module-import time unless this exact variable is present:

```text
NR2301_INTEGRATION=1
```

The administrator password must be supplied separately:

```text
NR2301_PASSWORD=<router admin password>
```

Optional variables:

```text
NR2301_URL=http://192.168.1.1
NR2301_USERNAME=admin
```

`NR2301_URL` and `NR2301_USERNAME` use those values as defaults when omitted.

## PowerShell example

```powershell
$env:NR2301_INTEGRATION = "1"
$env:NR2301_PASSWORD = "<password>"
$env:NR2301_URL = "http://192.168.1.1"

python -m pytest tests/integration/test_readonly_router.py -v
```

Remove the password from the environment afterwards:

```powershell
Remove-Item Env:NR2301_PASSWORD
Remove-Item Env:NR2301_INTEGRATION
```

## cmd.exe example

```bat
set NR2301_INTEGRATION=1
set NR2301_PASSWORD=<password>
set NR2301_URL=http://192.168.1.1
python -m pytest tests/integration/test_readonly_router.py -v
set NR2301_PASSWORD=
set NR2301_INTEGRATION=
```

## Linux/macOS example

```bash
NR2301_INTEGRATION=1 \
NR2301_PASSWORD='<password>' \
NR2301_URL='http://192.168.1.1' \
python -m pytest tests/integration/test_readonly_router.py -v
```

## CI behavior

GitHub Actions does not set `NR2301_INTEGRATION=1`, so the physical-router module is skipped and no network attempt is made toward the default router address.

A future write-integration suite, if added, should be a **separate second opt-in level** with explicit recovery prerequisites. It must not be enabled merely by the read-only `NR2301_INTEGRATION=1` flag.
