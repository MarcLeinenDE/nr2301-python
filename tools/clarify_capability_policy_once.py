# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

AGENTS = Path("AGENTS.md")
README = Path("README.md")
CHANGELOG = Path("CHANGELOG.md")

agents = AGENTS.read_text(encoding="utf-8")
anchor = (
    "A method may start as a close-to-wire namespace helper and later gain a more ergonomic high-level helper when semantics are sufficiently proven. "
    "The generic `client.call()` / `client.multicall()` APIs remain useful escape hatches, but they do not by themselves satisfy the long-term complete-SDK-coverage target.\n"
)
section = r'''

### Capability layer vs consumer policy

The SDK is a **capability layer**, not the product-policy layer for downstream applications.

If a local NR2301 capability is sufficiently reconstructed and evidence-backed, its risk classification is **not** a reason to omit it from the SDK. Safety metadata determines documentation, warnings, physical-test gates, recovery requirements and sensible helper design; it does not decide whether a verified router capability may exist in the reusable SDK.

Examples include Wi-Fi channel/bandwidth/power/SSID/security controls, LAN/DHCP, firewall/NAT, MAC filtering, traffic reset, VPN, SMS/phonebook, SIM/PIN/PUK, reboot and factory reset when their contracts are sufficiently established.

A downstream Android app, Home Assistant integration, CLI or other consumer decides its own policy: which SDK capabilities to expose, hide, require confirmation for, restrict to expert/admin mode, or omit entirely.

The earlier private NR2301 application is only a historical evidence source. Its feature set is **not** the SDK scope ceiling. Features that application never implemented must still be researched, physically verified where feasible, normalized upstream and added here when supported by the router.

The current USB-management-mode mutation exclusion is a temporary **test-campaign recovery constraint**, not a permanent SDK capability-policy exclusion. A verified USB-mode API may still be represented later once it can be tested without sacrificing the active recovery channel.
'''.strip("\n")
if section not in agents:
    agents = agents.replace(anchor, anchor + "\n" + section + "\n", 1)
AGENTS.write_text(agents, encoding="utf-8")

readme = README.read_text(encoding="utf-8")
readme = readme.replace(
    "`0.1.0.dev0` is the first SDK development baseline. It intentionally grows from the transport/authentication foundation into evidence-backed high-level helpers instead of pretending that all 157 documented API methods already have a stable Python wrapper.",
    "`0.1.0.dev0` is the current SDK development line. The long-term target is evidence-backed coverage of all locally usable NR2301 API capabilities, not just the feature set of the earlier private application. Safety classifications drive warnings/test gates/recovery behavior; downstream applications decide which SDK capabilities they expose.",
)
readme = readme.replace(
    "Planned next:\n\n- additional evidence-backed namespace helpers where they provide useful high-level behavior\n- first local run of the read-only integration suite against a physical NR2301\n- package/release audit before the first stable SDK release",
    "Planned next:\n\n- continue physical coverage of reversible and disruptive API capabilities, including Wi-Fi field-level controls that the earlier private app did not implement\n- close incomplete upstream contracts and expose every sufficiently evidenced local capability through the SDK\n- keep feeding all physical findings back into `nr2301-api` before the first stable SDK release audit",
)
readme = readme.replace('    "http://192.168.1.1",', '    "http://zyxel.home",')
readme = readme.replace(
    "PIN/PUK writes are intentionally not exposed. The public API classifies those paths as static-only / `DO_NOT_TEST_FOR_COVERAGE`, and retry exhaustion can lock a SIM.",
    "PIN/PUK writes are not exposed **yet** because their complete live contracts still need deliberate physical verification. They remain SDK coverage targets; retry-consuming tests require an explicit scenario and recovery plan rather than broad probing.",
)
readme = readme.replace(
    "The first integration suite is **read-only** and deliberately avoids high-sensitivity surfaces such as complete device identity, MAC inventory, Wi-Fi configuration/keys and SMS mailbox content.",
    "Physical tests are split into explicit risk tiers: read-only, reversible-write and destructive/recovery. Ordinary CI enables none of them. The dedicated test router is used to expand coverage while sensitive output is sanitized and USB-management-mode mutation remains temporarily excluded as the active recovery channel.",
)
README.write_text(readme, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
added_anchor = "### Added\n\n"
entry = "- clarified the SDK architecture as a complete router-capability layer: safety classifications control warnings/test gates/recovery requirements, while downstream apps/integrations decide which verified capabilities to expose; the older private app is evidence, not a feature-scope ceiling\n"
if entry not in changelog:
    changelog = changelog.replace(added_anchor, added_anchor + entry, 1)
validation_anchor = "### Physical validation\n\n"
validation = "- combined LAN/DHCP/DNS physical write test passed on 2026-08-31: DNS-only mutation preserved all seven non-DNS fields and the complete original 12-field object was restored exactly\n"
if validation not in changelog:
    changelog = changelog.replace(validation_anchor, validation_anchor + validation, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Clarified SDK capability policy and recorded DNS physical validation.")
