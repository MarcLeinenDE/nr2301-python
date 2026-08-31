# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

AGENTS = Path("AGENTS.md")
TEST = Path("tests/integration/test_wifi_field_writes.py")
CHANGELOG = Path("CHANGELOG.md")

agents = AGENTS.read_text(encoding="utf-8")
marker = "### Mandatory API feedback loop\n"
policy = """### Jurisdiction-neutral radio capabilities\n\nThis SDK is intended for worldwide use and must not hard-code Germany-, EU-, FCC-, or other jurisdiction-specific Wi-Fi channel, band or transmit-power policy merely because development/testing occurs in one country.\n\nExpose evidence-backed raw router capabilities and firmware-accepted option tokens. A capability being available through the SDK is **not** a claim that using it is lawful in every deployment. Deployment-specific regulatory policy belongs to the downstream consumer/integrator/operator and/or the router firmware's regulatory domain.\n\nDo not invent unsupported values and do not bypass firmware/hardware enforcement. If firmware rejects, masks or rewrites a radio setting, preserve and document that technical behavior upstream. Distinguish WebUI-proven option enums, runtime-advertised values, live-accepted values and exploratory candidates.\n\nPhysical testing on the dedicated non-production router may exercise technically evidenced or deliberately exploratory radio settings without applying a Germany/EU policy filter. The current USB-mode exclusion remains a recovery-channel constraint, not a regulatory restriction.\n\n"""
if policy not in agents and marker in agents:
    agents = agents.replace(marker, policy + marker, 1)
AGENTS.write_text(agents, encoding="utf-8")

text = TEST.read_text(encoding="utf-8")
if "_WEBUI_ENUM_CASES" not in text:
    insert = '''\n\n_WEBUI_ENUM_CASES = [\n    ("wifi_if_24G", "net_mode", ("11b", "11bg", "11bgn", "11bgnax")),\n    ("wifi_if_5G", "net_mode", ("11a", "11an", "11anac", "11anacax")),\n    ("wifi_if_24G", "bandwidth", ("HT20/HT40", "HT20", "HT40")),\n    ("wifi_if_5G", "bandwidth", ("HT20/HT40/HT80", "HT20", "HT40", "HT80")),\n]\n\n\ndef _adjacent_alternate(current: str, options: tuple[str, ...]) -> str:\n    assert current in options, f"router returned {current!r}, not in the original WebUI option contract"\n    index = options.index(current)\n    if index > 0:\n        return options[index - 1]\n    return options[1]\n'''
    text = text.replace("def _choose_24g_channel(block: dict) -> str:\n", insert + "\n\ndef _choose_24g_channel(block: dict) -> str:\n", 1)

if "def test_original_webui_radio_enum_change_and_restore" not in text:
    addition = '''\n\n@pytest.mark.parametrize(\n    ("section", "field", "options"),\n    _WEBUI_ENUM_CASES,\n    ids=["24g-net-mode", "5g-net-mode", "24g-bandwidth", "5g-bandwidth"],\n)\ndef test_original_webui_radio_enum_change_and_restore(\n    section: str, field: str, options: tuple[str, ...]\n) -> None:\n    router = _client()\n    try:\n        original = copy.deepcopy(_config(router)[section])\n        current = str(original[field])\n        target = _adjacent_alternate(current, options)\n        try:\n            actual = router.wifi.update_ap_section(section, {field: target})\n            assert str(actual.get(field)) == target\n        finally:\n            _restore_section(router, section, original)\n    finally:\n        router.close()\n'''
    text = text.rstrip() + addition + "\n"
TEST.write_text(text, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
entry = "- added jurisdiction-neutral radio-capability policy and physical Wi-Fi write/restore coverage for the original WebUI 2.4/5-GHz net-mode and bandwidth enums; the SDK does not impose Germany/EU-specific radio limits\n"
marker = "### Added\n\n"
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Patched jurisdiction-neutral policy and Wi-Fi WebUI enum tests.")
