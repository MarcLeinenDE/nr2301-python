# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

FILES = [
    Path("tests/integration/test_wifi_field_writes.py"),
    Path("tests/integration/test_wifi_extended_writes.py"),
]
CHANGELOG = Path("CHANGELOG.md")

old = '''def _mismatched_fields(actual: dict, expected: dict) -> list[str]:\n    return sorted(\n        key\n        for key in set(actual) | set(expected)\n        if actual.get(key) != expected.get(key)\n    )\n\n\ndef _restore_section(router: NR2301Client, section: str, original: dict) -> None:\n    current = _config(router).get(section)\n    if current != original:\n        router.wifi.update_ap_section(section, original)\n    final = _config(router).get(section)\n    if not isinstance(final, dict):\n        pytest.fail(f"{section} restore returned no mapping")\n    if final != original:\n        # Never let pytest introspection print complete AP blocks: they can\n        # contain the real SSID and Wi-Fi key. Field names are sufficient.\n        pytest.fail(\n            f"{section} restore mismatch in fields: "\n            f"{_mismatched_fields(final, original)}"\n        )\n'''

new = '''_NON_CONFIG_FIELDS = {\n    "wifi_if_24G": {"cur_channel", "first_channel", "last_channel"},\n    "wifi_if_5G": {"cur_channel", "channel_list"},\n}\n\n\ndef _configurable_view(section: str, block: dict) -> dict:\n    ignored = _NON_CONFIG_FIELDS.get(section, set())\n    return {key: value for key, value in block.items() if key not in ignored}\n\n\ndef _mismatched_fields(actual: dict, expected: dict) -> list[str]:\n    return sorted(\n        key\n        for key in set(actual) | set(expected)\n        if actual.get(key) != expected.get(key)\n    )\n\n\ndef _restore_section(router: NR2301Client, section: str, original: dict) -> None:\n    expected = _configurable_view(section, original)\n    current = _config(router).get(section)\n    if not isinstance(current, dict):\n        pytest.fail(f"{section} restore current state returned no mapping")\n    if _configurable_view(section, current) != expected:\n        router.wifi.update_ap_section(section, expected)\n    final = _config(router).get(section)\n    if not isinstance(final, dict):\n        pytest.fail(f"{section} restore returned no mapping")\n    final_view = _configurable_view(section, final)\n    if final_view != expected:\n        # Runtime/capability fields such as cur_channel are deliberately not\n        # restore targets. Only mutable configuration differences are reported.\n        pytest.fail(\n            f"{section} restore mismatch in configurable fields: "\n            f"{_mismatched_fields(final_view, expected)}"\n        )\n'''

for path in FILES:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected restore helper not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
anchor = "### Fixed / corrected\n\n"
entry = "- corrected Wi-Fi restore semantics after physical security-matrix evidence showed `cur_channel` can legitimately differ after restoring configured auto-channel state; physical restore helpers now compare only mutable configuration and exclude runtime/capability metadata (`cur_channel`, `first_channel`, `last_channel`, `channel_list`)\n"
if entry not in changelog:
    changelog = changelog.replace(anchor, anchor + entry, 1)
added_anchor = "### Added\n\n"
added_entry = "- enhanced `examples/explore_wifi_security_matrix.py` with per-case checkpoint reports and `NR2301_SECURITY_START=SECTION:TOKEN` resume support so completed physical cases are not repeated after an interruption\n"
if added_entry not in changelog:
    changelog = changelog.replace(added_anchor, added_anchor + added_entry, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Corrected Wi-Fi restore semantics and documented security-matrix resume support.")
