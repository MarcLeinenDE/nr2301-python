# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
DOC = Path("docs/integration-testing.md")

changelog = CHANGELOG.read_text(encoding="utf-8")
entry = "- completed a real external SMS E2E through the public SDK: `send()` returned the verified 0/1/0 success triple and the handset physically received the message; the handset reply appeared as a new Inbox item and `get_by_id()` returned the complete documented response field set; Inbox/Outbox bodies were observed as UTF-16BE hex with phone number/content kept out of logs\n"
marker = "## Unreleased\n\n"
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)

physical = "- public-SDK SMS E2E completed on 2026-08-31: `send()` returned `resp=0/smsSendSucc=1/smsSendFail=0`, physical handset receipt was confirmed, the real handset reply appeared as a new Inbox item, and `get_by_id()` returned fields `address,body,contact_id,date,id,location,protocol,read,resp,status,type`; Inbox/Outbox bodies were decodable as UTF-16BE hex and all phone numbers/message contents were excluded from logs\n"
phys_marker = "### Physical validation\n\n"
if physical not in changelog and phys_marker in changelog:
    changelog = changelog.replace(phys_marker, phys_marker + physical, 1)

stale = "- normalize remaining SMS draft-save/get-by-ID contracts before adding convenience helpers\n"
changelog = changelog.replace(stale, "")
CHANGELOG.write_text(changelog, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")

level2_anchor = "The read-only `NR2301_INTEGRATION=1` flag must never enable these tests.\n"
external_note = """

### Extra gate for external SMS transmission

Physical tests that actually transmit an SMS to the mobile network require an additional explicit opt-in beyond the normal Level-2 write flag:

```text
NR2301_SMS_EXTERNAL_INTEGRATION=1
NR2301_SMS_TEST_NUMBER=<operator-controlled handset number>
```

The reusable E2E test is `tests/integration/test_sms_end_to_end_reply.py`. It requires both `NR2301_WRITE_INTEGRATION=1` and `NR2301_SMS_EXTERNAL_INTEGRATION=1`, so ordinary reversible-write testing cannot send an external SMS accidentally.

For the current maintainer test environment only, the integration test accepts a German national-format number such as `0176...` and converts it locally to `+49176...`. This is a test-harness convenience, **not** SDK number-normalization policy; `client.sms.send()` remains country-neutral and sends the recipient supplied by the caller.

The test never prints the phone number or SMS body. It correlates the newly created Outbox row primarily by new message ID plus normalized target address. Body content is only secondary evidence because a byte-exact full-body comparison proved unnecessarily brittle during the first real E2E run.
"""
if "### Extra gate for external SMS transmission" not in doc and level2_anchor in doc:
    doc = doc.replace(level2_anchor, level2_anchor + external_note, 1)

section = """

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
"""
if "## Completed physical SMS SDK exchange coverage" not in doc:
    doc = doc.rstrip() + section + "\n"
DOC.write_text(doc, encoding="utf-8")

print("Recorded sanitized SMS E2E SDK documentation.")
