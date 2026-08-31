# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

TEST_FILES = [
    Path("tests/integration/test_wifi_field_writes.py"),
    Path("tests/integration/test_wifi_extended_writes.py"),
]
CHANGELOG = Path("CHANGELOG.md")

old_restore = '''def _restore_section(router: NR2301Client, section: str, original: dict) -> None:\n    current = _config(router).get(section)\n    if current != original:\n        router.wifi.update_ap_section(section, original)\n    assert _config(router).get(section) == original\n'''

new_restore = '''def _mismatched_fields(actual: dict, expected: dict) -> list[str]:\n    return sorted(\n        key\n        for key in set(actual) | set(expected)\n        if actual.get(key) != expected.get(key)\n    )\n\n\ndef _restore_section(router: NR2301Client, section: str, original: dict) -> None:\n    current = _config(router).get(section)\n    if current != original:\n        router.wifi.update_ap_section(section, original)\n    final = _config(router).get(section)\n    if not isinstance(final, dict):\n        pytest.fail(f"{section} restore returned no mapping")\n    if final != original:\n        # Never let pytest introspection print complete AP blocks: they can\n        # contain the real SSID and Wi-Fi key. Field names are sufficient.\n        pytest.fail(\n            f"{section} restore mismatch in fields: "\n            f"{_mismatched_fields(final, original)}"\n        )\n'''

for path in TEST_FILES:
    text = path.read_text(encoding="utf-8")
    if old_restore in text:
        text = text.replace(old_restore, new_restore, 1)
    elif "def _mismatched_fields(" not in text:
        raise SystemExit(f"expected restore helper not found in {path}")
    path.write_text(text, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
added_anchor = "### Added\n\n"
added_entry = "- added `examples/explore_wifi_security_matrix.py`, a hard-gated sanitized 13-token × 4-section Wi-Fi security explorer that classifies accepted/coerced/unverified results, uses only synthetic keys, restores every AP block and writes a shareable credential-free JSON report while tracking the raw `password_modified` marker\n"
if added_entry not in changelog:
    changelog = changelog.replace(added_anchor, added_anchor + added_entry, 1)

physical_anchor = "### Physical validation\n\n"
physical_entry = "- extended Wi-Fi capability suite passed on 2026-08-31: all 18 cases passed in 226.96 s, confirming raw `power_level` values 0/1/2, global and Guest maxassoc=1, Guest 2.4G/5G band mode, synthetic SSID writes on all four AP blocks, 2.4-GHz channel 13, 5-GHz channels 52/100/140 including DFS-class paths, every source-known WebUI net-mode/bandwidth token, and normal-admin `wifi_scan`, with original state restored after every mutation\n"
if physical_entry not in changelog:
    changelog = changelog.replace(physical_anchor, physical_anchor + physical_entry, 1)

fixed_anchor = "### Fixed / corrected\n\n"
fixed_entry = "- hardened physical Wi-Fi restore assertions so a failed restore reports only mismatching field names instead of allowing pytest to render complete AP dictionaries containing real SSIDs/keys\n"
if fixed_entry not in changelog:
    changelog = changelog.replace(fixed_anchor, fixed_anchor + fixed_entry, 1)

stale = "- run the extended Wi-Fi capability matrix and normalize accepted/rejected `power_level`, DFS/boundary-channel, Guest-band/max-client and exhaustive WebUI enum results upstream\n"
changelog = changelog.replace(stale, "")

old_security = "- physically verify Wi-Fi credential/security mutation separately with synthetic SSIDs/keys while tracking whether `password_modified` changes persistently\n"
new_security = "- run the sanitized 13-token × 4-section Wi-Fi encryption/key matrix, normalize accepted/coerced/rejected behavior upstream and determine from physical transitions whether the raw `password_modified` marker is a persistent latch or another state indicator\n"
changelog = changelog.replace(old_security, new_security)

CHANGELOG.write_text(changelog, encoding="utf-8")
print("Prepared secret-safe restore assertions and Wi-Fi security-matrix documentation.")
