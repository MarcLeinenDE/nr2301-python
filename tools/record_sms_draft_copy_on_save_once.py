# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

SMS = Path("src/nr2301/namespaces/sms.py")
TEST = Path("tests/integration/test_sms_draft_get_by_id.py")
CHANGELOG = Path("CHANGELOG.md")
DOC = Path("docs/integration-testing.md")

sms = SMS.read_text(encoding="utf-8")
old = '''        """Create or update a normal-protocol SMS draft.\n\n        The exact live-verified draft contract uses type=2 and protocol=0.\n        `message_id=-1` creates a new draft; an existing non-negative ID\n        updates that draft. Recipient/message values are never included in\n        SDK-generated error metadata.\n        """'''
new = '''        """Save a normal-protocol SMS draft using the shipped frontend contract.\n\n        The exact live-verified draft contract uses type=2 and protocol=0.\n        `message_id=-1` creates a new Draft. The shipped frontend passes the\n        current Draft ID when saving an edited Draft, but on the physically\n        tested ACIY.3 firmware that existing-ID path is COPY_ON_SAVE: the\n        original Draft remains unchanged and a new Draft ID is created. Do\n        not assume in-place update semantics on other firmware without\n        evidence. Recipient/message values are never included in SDK-generated\n        error metadata.\n        """'''
if old not in sms:
    raise SystemExit("expected save_draft docstring not found")
sms = sms.replace(old, new, 1)
SMS.write_text(sms, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
test = test.replace(
    "def test_sms_draft_create_get_update_delete_roundtrip() -> None:",
    "def test_sms_draft_create_get_existing_id_copy_delete_roundtrip() -> None:",
    1,
)
TEST.write_text(test, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
entry = "- live-profiled `save_draft(..., message_id=<existing>)` on ACIY.3: the shipped-frontend existing-ID request returns the verified save success triple but behaves as COPY_ON_SAVE (original Draft unchanged, exactly one new Draft ID contains the replacement body); SDK documentation no longer promises in-place update semantics\n"
marker = "## Unreleased\n\n"
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
section = '''\n\n## SMS Draft existing-ID semantics — 2026-08-31\n\nThe public SDK physically profiled `client.sms.save_draft(..., message_id=<existing Draft ID>)` on ACIY.3. The shipped frontend does send the current Draft ID when saving an edited Draft, but the tested firmware did not mutate that record in place:\n\n```text\ncreate Draft A                    success 0/1/0\nget_by_id(original ID)            body class A\nsave Draft B with original ID     success 0/1/0\nget_by_id(original ID)            still body class A\nnew Draft IDs                     exactly 1\nget_by_id(new ID)                 body class B\nbehavior                          COPY_ON_SAVE\ncleanup                           both synthetic IDs deleted\n```\n\nThe Draft list and Draft `get_by_id` responses returned bare addresses (without the trailing comma used on the save wire), UTF-16BE-hex bodies and `type=2`. Tests log only representation/body classes and never recipient or body values.\n\nThe SDK keeps the `message_id` parameter because it is part of the source-backed capability contract, but callers must not assume that an existing ID means in-place update on every firmware.\n'''
if "## SMS Draft existing-ID semantics — 2026-08-31" not in doc:
    doc = doc.rstrip() + section + "\n"
DOC.write_text(doc, encoding="utf-8")

print("Recorded SDK SMS Draft COPY_ON_SAVE evidence.")
