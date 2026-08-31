# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

WIFI = Path("src/nr2301/namespaces/wifi.py")
FIELD_TEST = Path("tests/integration/test_wifi_field_writes.py")
TEST_REDACTION = Path("tests/test_wifi_redaction.py")
CHANGELOG = Path("CHANGELOG.md")

text = WIFI.read_text(encoding="utf-8")

anchor = "_GUEST_VERIFY_FIELDS = (\n    \"band_mode\",\n    \"ssid\",\n    \"hidden\",\n    \"encryption\",\n    \"key\",\n    \"maxassoc\",\n)\n"
if "_WIFI_SECRET_FIELDS" not in text:
    text = text.replace(anchor, anchor + "\n_WIFI_SECRET_FIELDS = {\"ssid\", \"key\", \"password\", \"passphrase\", \"psk\", \"secret\"}\n")

old_details = '''        details: dict[str, Any] = {\n            "section": section,\n            "expected_changes": dict(changes),\n            "actual": last_actual,\n        }\n'''
new_details = '''        details: dict[str, Any] = {\n            "section": section,\n            "expected_changes": self._redact_wifi_value(dict(changes)),\n            "actual": self._redact_wifi_value(last_actual),\n        }\n'''
text = text.replace(old_details, new_details)

insert_before = "    def set_wps_enabled(\n"
if "def update_global_settings(" not in text:
    method = '''    def update_global_settings(\n        self,\n        changes: Mapping[str, Any],\n        *,\n        write_timeout: float = 30.0,\n        recovery_attempts: int = 10,\n        recovery_delay: float = 1.0,\n        recovery_timeout: float = 3.0,\n    ) -> WiFiAPConfigResponse:\n        """Update evidenced top-level AP settings with recovery/read-back.\n\n        Supported fields are currently `switch`, `maxassoc` and `power_level`.\n        `mode` has dedicated state-machine helpers because it requires AP-block\n        preservation.\n        """\n\n        allowed = {"switch", "maxassoc", "power_level"}\n        if not isinstance(changes, Mapping) or not changes:\n            raise ValueError("changes must be a non-empty mapping")\n        unknown = set(changes) - allowed\n        if unknown:\n            raise ValueError(f"unsupported top-level Wi-Fi setting(s): {sorted(unknown)!r}")\n        self._validate_recovery_args(\n            write_timeout, recovery_attempts, recovery_delay, recovery_timeout\n        )\n\n        before = self.config()\n        before_config = self._extract_config(before)\n        if all(str(before_config.get(key)) == str(value) for key, value in changes.items()):\n            return before\n\n        write_error: NR2301Error | None = None\n        try:\n            self._client.call(\n                "wireless",\n                "wifi_set_ap_config",\n                data=dict(changes),\n                timeout=write_timeout,\n            )\n        except (TransportError, ProtocolError) as exc:\n            write_error = exc\n\n        last_actual: WiFiAPConfigResponse | None = None\n        last_error: NR2301Error | None = None\n        for attempt in range(recovery_attempts):\n            try:\n                actual = self.config(timeout=recovery_timeout)\n                last_actual = actual\n                config = self._extract_config(actual)\n                if all(str(config.get(key)) == str(value) for key, value in changes.items()):\n                    return actual\n            except NR2301Error as exc:\n                last_error = exc\n                last_error = self._try_relogin(last_error)\n            if attempt + 1 < recovery_attempts and recovery_delay:\n                time.sleep(recovery_delay)\n\n        details: dict[str, Any] = {\n            "expected_changes": self._redact_wifi_value(dict(changes)),\n            "actual": self._redact_wifi_value(last_actual),\n        }\n        if write_error is not None:\n            details["write_transport_error"] = type(write_error).__name__\n        if last_error is not None:\n            details["last_recovery_error"] = type(last_error).__name__\n        raise APIError(\n            "top-level Wi-Fi setting could not be verified by read-back",\n            method_id="wireless/wifi_set_ap_config",\n            response=details,\n        )\n\n'''
    text = text.replace(insert_before, method + insert_before)

helper_anchor = "    @staticmethod\n    def _extract_wps_enable(response: Mapping[str, Any]) -> str:\n"
if "def _redact_wifi_value(" not in text:
    helper = '''    @staticmethod\n    def _redact_wifi_value(value: Any, *, field: str | None = None) -> Any:\n        if field is not None and field.lower() in _WIFI_SECRET_FIELDS:\n            return "<redacted>"\n        if isinstance(value, Mapping):\n            return {\n                str(key): WiFiNamespace._redact_wifi_value(item, field=str(key))\n                for key, item in value.items()\n            }\n        if isinstance(value, list):\n            return [WiFiNamespace._redact_wifi_value(item) for item in value]\n        return value\n\n'''
    text = text.replace(helper_anchor, helper + helper_anchor)

WIFI.write_text(text, encoding="utf-8")

field = FIELD_TEST.read_text(encoding="utf-8")
field = field.replace("import copy\nimport os\n", "import copy\nimport os\nfrom datetime import datetime, timedelta\n")
field = field.replace(
    '@pytest.mark.parametrize("section", ["wifi_if_24G", "wifi_if_5G"])\ndef test_hidden_toggle_and_restore',
    '@pytest.mark.parametrize("section", ["wifi_if_24G", "wifi_if_5G", "wifi_if_DUAL", "wifi_if_GUEST"])\ndef test_hidden_toggle_and_restore',
)
old_global = '''        try:\n            router.call(\n                "wireless",\n                "wifi_set_ap_config",\n                data={"maxassoc": target},\n                timeout=30.0,\n            )\n            assert str(_config(router).get("maxassoc")) == target\n        finally:\n            if str(_config(router).get("maxassoc")) != original:\n                router.call(\n                    "wireless",\n                    "wifi_set_ap_config",\n                    data={"maxassoc": original},\n                    timeout=30.0,\n                )\n            assert str(_config(router).get("maxassoc")) == original\n'''
new_global = '''        try:\n            actual = router.wifi.update_global_settings({"maxassoc": target})\n            assert str(actual["config"].get("maxassoc")) == target\n        finally:\n            if str(_config(router).get("maxassoc")) != original:\n                router.wifi.update_global_settings({"maxassoc": original})\n            assert str(_config(router).get("maxassoc")) == original\n'''
field = field.replace(old_global, new_global)
old_schedule = '''        if target["enable"] == 1:\n            # A short, valid-looking schedule that should not overlap the\n            # current local time for long. We test persistence, not timer fire.\n            target.update({\n                "start_hour": 3,\n                "start_minute": 17,\n                "end_hour": 3,\n                "end_minute": 19,\n            })\n'''
new_schedule = '''        if target["enable"] == 1:\n            # Place the test window six hours ahead of the PC clock so the\n            # schedule is not expected to fire during this short persistence test.\n            start = datetime.now() + timedelta(hours=6)\n            end = start + timedelta(minutes=2)\n            target.update({\n                "start_hour": start.hour,\n                "start_minute": start.minute,\n                "end_hour": end.hour,\n                "end_minute": end.minute,\n            })\n'''
field = field.replace(old_schedule, new_schedule)

if "def test_master_switch_off_and_restore" not in field:
    field += '''\n\ndef test_master_switch_off_and_restore() -> None:\n    router = _client()\n    try:\n        original = str(_config(router)["switch"])\n        assert original in {"on", "off"}\n        target = "off" if original == "on" else "on"\n        try:\n            actual = router.wifi.update_global_settings({"switch": target})\n            assert str(actual["config"].get("switch")) == target\n        finally:\n            if str(_config(router).get("switch")) != original:\n                router.wifi.update_global_settings({"switch": original})\n            assert str(_config(router).get("switch")) == original\n    finally:\n        router.close()\n'''
FIELD_TEST.write_text(field, encoding="utf-8")

TEST_REDACTION.write_text('''from nr2301.namespaces.wifi import WiFiNamespace\n\n\ndef test_wifi_redaction_hides_nested_ssid_and_key():\n    value = {\n        "ssid": "PrivateName",\n        "key": "PrivateKey",\n        "channel": "6",\n        "nested": {"password": "secret", "hidden": "0"},\n    }\n    redacted = WiFiNamespace._redact_wifi_value(value)\n    assert redacted == {\n        "ssid": "<redacted>",\n        "key": "<redacted>",\n        "channel": "6",\n        "nested": {"password": "<redacted>", "hidden": "0"},\n    }\n''', encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
entry = "- hardened Wi-Fi write diagnostics so SSID/key/password-like fields are redacted from verification failures, and added a recovery/read-back helper for top-level Wi-Fi settings used by the physical capability campaign\n"
marker = "### Fixed / corrected\n\n"
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Patched Wi-Fi write diagnostics and field tests.")
