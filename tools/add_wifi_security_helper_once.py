# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

WIFI = Path("src/nr2301/namespaces/wifi.py")
TESTS = Path("tests/test_wifi_namespace.py")
CHANGELOG = Path("CHANGELOG.md")

wifi = WIFI.read_text(encoding="utf-8")

if "WiFiSecurity = Literal[" not in wifi:
    anchor = "\n\n_ALLOWED_AP_SECTIONS = {"
    security_type = '''\n\nWiFiSecurity = Literal[\n    "psk-mixed+ccmp",\n    "sae-mixed",\n    "sae",\n    "psk2+ccmp",\n    "psk+ccmp",\n    "psk2+tkip+ccmp",\n    "psk+tkip+ccmp",\n    "psk-mixed+tkip+ccmp",\n    "psk2+tkip",\n    "psk+tkip",\n    "psk-mixed+tkip",\n    "wep-mixed",\n    "none",\n]\n'''
    if anchor not in wifi:
        raise SystemExit("WiFi type insertion anchor not found")
    wifi = wifi.replace(anchor, security_type + anchor, 1)

if "_VERIFIED_WIFI_ENCRYPTION_TOKENS" not in wifi:
    anchor = "_VERIFIED_WIFI_MODES = {"
    constants = '''_SECURITY_AP_SECTIONS = {\n    "wifi_if_24G",\n    "wifi_if_5G",\n    "wifi_if_DUAL",\n    "wifi_if_GUEST",\n}\n_VERIFIED_WIFI_ENCRYPTION_TOKENS = {\n    "psk-mixed+ccmp",\n    "sae-mixed",\n    "sae",\n    "psk2+ccmp",\n    "psk+ccmp",\n    "psk2+tkip+ccmp",\n    "psk+tkip+ccmp",\n    "psk-mixed+tkip+ccmp",\n    "psk2+tkip",\n    "psk+tkip",\n    "psk-mixed+tkip",\n    "wep-mixed",\n    "none",\n}\n'''
    if anchor not in wifi:
        raise SystemExit("WiFi constants insertion anchor not found")
    wifi = wifi.replace(anchor, constants + anchor, 1)

if "    def set_security(" not in wifi:
    anchor = "    def update_ap_section(\n"
    method = '''    def set_security(\n        self,\n        section: APSection,\n        encryption: WiFiSecurity,\n        key: str | None = None,\n        *,\n        write_timeout: float = 30.0,\n        recovery_attempts: int = 10,\n        recovery_delay: float = 1.0,\n        recovery_timeout: float = 3.0,\n    ) -> dict[str, Any]:\n        """Set a live-verified Wi-Fi security token and optional key.\n\n        All 13 source-known encryption tokens were physically accepted on\n        24G, 5G, DUAL and Guest AP sections on ACIY.3. Protected modes require\n        a non-empty key and verify both token and key through the existing\n        AP-section read-back path.\n\n        Open mode (``encryption=\"none\"``) is intentionally special: ACIY.3\n        accepts the open-mode token on all four sections, but 24G/5G/DUAL do\n        not necessarily clear/read back ``key=\"\"``. Therefore the SDK sends\n        and verifies only the encryption token for open mode rather than\n        inventing a universal empty-key invariant.\n\n        Key length/format rules are deliberately not over-validated here: the\n        public evidence proves token acceptance and representative synthetic\n        keys, but not a complete per-security-mode key-format matrix. Firmware\n        rejection remains authoritative.\n        """\n\n        if section not in _SECURITY_AP_SECTIONS:\n            raise ValueError(f"unsupported Wi-Fi security section: {section!r}")\n        if encryption not in _VERIFIED_WIFI_ENCRYPTION_TOKENS:\n            raise ValueError(f"unsupported/unverified Wi-Fi encryption token: {encryption!r}")\n\n        if encryption == "none":\n            if key not in (None, ""):\n                raise ValueError("open Wi-Fi mode does not accept a key argument")\n            changes: dict[str, Any] = {"encryption": "none"}\n        else:\n            if not isinstance(key, str) or not key:\n                raise ValueError("a non-empty key is required for protected Wi-Fi modes")\n            changes = {"encryption": encryption, "key": key}\n\n        return self.update_ap_section(\n            section,\n            changes,\n            write_timeout=write_timeout,\n            recovery_attempts=recovery_attempts,\n            recovery_delay=recovery_delay,\n            recovery_timeout=recovery_timeout,\n        )\n\n'''
    if anchor not in wifi:
        raise SystemExit("set_security insertion anchor not found")
    wifi = wifi.replace(anchor, method + anchor, 1)

WIFI.write_text(wifi, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_set_security_protected_mode_verifies_token_and_key" not in tests:
    tests += '''\n\n\ndef test_set_security_protected_mode_verifies_token_and_key():\n    before = {\n        "config": {\n            "wifi_if_24G": {\n                "ssid": "Synthetic",\n                "encryption": "psk-mixed+ccmp",\n                "key": "old-secret",\n                "hidden": "0",\n            }\n        }\n    }\n    after = {\n        "config": {\n            "wifi_if_24G": {\n                "ssid": "Synthetic",\n                "encryption": "sae",\n                "key": "new-synthetic-secret",\n                "hidden": "0",\n            }\n        }\n    }\n    client, session = authenticated_client(before, {"result": 0}, after)\n\n    result = client.wifi.set_security(\n        "wifi_if_24G",\n        "sae",\n        "new-synthetic-secret",\n        recovery_delay=0,\n    )\n\n    assert result["encryption"] == "sae"\n    assert result["key"] == "new-synthetic-secret"\n    payload = session.calls[1][2]["json"]["wifi_if_24G"]\n    assert payload["ssid"] == "Synthetic"\n    assert payload["encryption"] == "sae"\n    assert payload["key"] == "new-synthetic-secret"\n\n\ndef test_set_security_open_mode_does_not_require_key_to_clear():\n    before = {\n        "config": {\n            "wifi_if_5G": {\n                "ssid": "Synthetic",\n                "encryption": "psk-mixed+ccmp",\n                "key": "retained-internal-secret",\n            }\n        }\n    }\n    after = {\n        "config": {\n            "wifi_if_5G": {\n                "ssid": "Synthetic",\n                "encryption": "none",\n                "key": "retained-internal-secret",\n            }\n        }\n    }\n    client, session = authenticated_client(before, {"result": 0}, after)\n\n    result = client.wifi.set_security("wifi_if_5G", "none", recovery_delay=0)\n\n    assert result["encryption"] == "none"\n    assert result["key"] == "retained-internal-secret"\n    payload = session.calls[1][2]["json"]["wifi_if_5G"]\n    assert payload["encryption"] == "none"\n    assert payload["key"] == "retained-internal-secret"\n\n\ndef test_set_security_rejects_key_for_open_mode_before_network_access():\n    client, session = authenticated_client()\n\n    with pytest.raises(ValueError, match="open Wi-Fi mode does not accept a key"):\n        client.wifi.set_security("wifi_if_DUAL", "none", "should-not-be-used")\n\n    assert session.calls == []\n\n\ndef test_set_security_requires_key_for_protected_mode_before_network_access():\n    client, session = authenticated_client()\n\n    with pytest.raises(ValueError, match="non-empty key is required"):\n        client.wifi.set_security("wifi_if_GUEST", "sae-mixed")\n\n    assert session.calls == []\n\n\ndef test_set_security_rejects_unknown_token_before_network_access():\n    client, session = authenticated_client()\n\n    with pytest.raises(ValueError, match="unsupported/unverified Wi-Fi encryption token"):\n        client.wifi.set_security(\n            "wifi_if_24G",\n            "future-security",  # type: ignore[arg-type]\n            "synthetic-key",\n        )\n\n    assert session.calls == []\n'''
TESTS.write_text(tests, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
added_anchor = "### Added\n\n"
added_entry = "- added `client.wifi.set_security()` with all 13 physically verified encryption tokens on 24G/5G/DUAL/Guest; protected modes verify token+key, while open mode correctly verifies only `encryption=none` because ACIY.3 can retain a non-empty key field on 24G/5G/DUAL\n"
if added_entry not in changelog:
    changelog = changelog.replace(added_anchor, added_anchor + added_entry, 1)

physical_anchor = "### Physical validation\n\n"
physical_entry = "- complete Wi-Fi security matrix finished on 2026-08-31: 52/52 section/token combinations accepted; every protected mode round-tripped the synthetic key on all four AP sections, open mode exposed section-specific key-field behavior, and `password_modified` remained 0 throughout\n"
if physical_entry not in changelog:
    changelog = changelog.replace(physical_anchor, physical_anchor + physical_entry, 1)

old = "- run the sanitized 13-token × 4-section Wi-Fi encryption/key matrix, normalize accepted/coerced/rejected behavior upstream and determine from physical transitions whether the raw `password_modified` marker is a persistent latch or another state indicator\n"
changelog = changelog.replace(old, "- determine the exact meaning of the raw `password_modified` field; the complete 52-case security campaign proved it is not a generic Wi-Fi credential-change latch\n")
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Added live-verified Wi-Fi security helper and offline tests.")
