# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations
from pathlib import Path

CHANGELOG = Path('CHANGELOG.md')
DOC = Path('docs/integration-testing.md')

changelog = CHANGELOG.read_text(encoding='utf-8')
entry = "- SIM `provide_pin` lifecycle test passed on 2026-08-31 in 76.02 s: after enabling PIN protection, a real reboot outage was confirmed, administrator login recovered on attempt 27, the SIM stabilized at `pin_status=2`, one known-correct local PIN returned `response.setting_response=OK`, read-back returned to `pin_status=5`, retry counters remained 3/10, and PIN protection was restored to disabled\n"
marker = "### Physical validation\n\n"
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
backlog_old = "- physically validate the new SIM PIN helpers with known locally supplied credentials and retry guards; keep PUK-reset testing recovery-only rather than manufacturing a blocked SIM merely for coverage\n"
backlog_new = "- SIM `enable_pin`, `disable_pin`, `change_pin` and `provide_pin` are physically verified with known local credentials and unchanged retry budgets; keep `reset_pin_using_puk` recovery-only rather than manufacturing a blocked SIM merely for coverage\n"
changelog = changelog.replace(backlog_old, backlog_new)
CHANGELOG.write_text(changelog, encoding='utf-8')

doc = DOC.read_text(encoding='utf-8')
section = """
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
""".strip()
if "## Completed physical SIM PIN lifecycle coverage — 2026-08-31" not in doc:
    doc = doc.rstrip() + "\n\n" + section + "\n"
DOC.write_text(doc, encoding='utf-8')

print('Recorded SIM provide-PIN physical evidence in SDK docs.')
