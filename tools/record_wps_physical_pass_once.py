# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
INTEGRATION_DOC = Path("docs/integration-testing.md")

changelog = CHANGELOG.read_text(encoding="utf-8")
anchor = "### Physical validation\n\n"
entry = "- WPS action integration passed on 2026-08-31 in 1.44 s: PBC returned nested `wireless.wps_call_pbc_result=OK`, Cancel returned flat top-level `wps_call_cancel_result=OK`, PIN `12345670` returned nested `wireless.wps_call_pin_result=OK`, the second Cancel was again flat/OK, and the original WPS-enable state was restored\n"
if entry not in changelog:
    changelog = changelog.replace(anchor, anchor + entry, 1)

fixed_duplicate = "\n### Fixed\n\n- fixed WPS action response handling after physical ACIY.3 evidence showed `wifi_call_wps_cancel` returning a flat top-level `wps_call_cancel_result` while PBC returned its result under `wireless`; helpers now accept either evidenced envelope but still require the action result to be exactly `OK`\n"
if fixed_duplicate in changelog:
    changelog = changelog.replace(fixed_duplicate, "")
    fixed_anchor = "### Fixed / corrected\n\n"
    fixed_entry = "- fixed WPS action response handling after physical ACIY.3 evidence showed action-specific response envelopes: PBC/PIN return their `OK` results under `wireless`, while Cancel returns flat top-level `wps_call_cancel_result=OK`; helpers accept either physically evidenced envelope while still requiring the exact action result\n"
    if fixed_entry not in changelog:
        changelog = changelog.replace(fixed_anchor, fixed_anchor + fixed_entry, 1)

CHANGELOG.write_text(changelog, encoding="utf-8")

if INTEGRATION_DOC.exists():
    doc = INTEGRATION_DOC.read_text(encoding="utf-8")
    block = """
## Completed physical Wireless action coverage — 2026-08-31

The dedicated-router WPS action test passed end-to-end in `1.44 s`:

```text
PBC              -> wireless.wps_call_pbc_result = OK
Cancel after PBC -> top-level wps_call_cancel_result = OK
PIN 12345670     -> wireless.wps_call_pin_result = OK
Cancel after PIN -> top-level wps_call_cancel_result = OK
```

The original WPS-enable state was restored. Together with the preceding Wi-Fi configuration/security campaigns, the 14-method public `wireless` API namespace now has explicit SDK surface coverage and physical end-to-end evidence for its action wrappers.
"""
    if "## Completed physical Wireless action coverage — 2026-08-31" not in doc:
        doc = doc.rstrip() + "\n\n" + block.strip() + "\n"
        INTEGRATION_DOC.write_text(doc, encoding="utf-8")

print("Recorded successful physical WPS action integration pass.")
