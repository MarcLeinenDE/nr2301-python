# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

WIFI = Path("src/nr2301/namespaces/wifi.py")
TESTS = Path("tests/test_wifi_namespace.py")
INTEGRATION = Path("tests/integration/test_wps_actions.py")
CHANGELOG = Path("CHANGELOG.md")

wifi = WIFI.read_text(encoding="utf-8")

old_type = '''class WPSActionResponse(TypedDict, total=False):\n    wireless: WPSActionWireless\n'''
new_type = '''class WPSActionResponse(TypedDict, total=False):\n    # ACIY.3 has been observed to use both response shapes across WPS actions:\n    # nested under `wireless` and flat at the top level. Preserve the raw shape.\n    wireless: WPSActionWireless\n    wps_call_pbc_result: str\n    wps_call_pin_result: str\n    wps_call_cancel_result: str\n'''
if old_type in wifi:
    wifi = wifi.replace(old_type, new_type, 1)

old_helper = '''    @staticmethod\n    def _require_wps_action_ok(response: Mapping[str, Any], field: str) -> None:\n        wireless = response.get("wireless")\n        if not isinstance(wireless, Mapping) or wireless.get(field) != "OK":\n            raise APIError(\n                f"WPS action did not return {field}=OK",\n                method_id="wireless/WPS_ACTION",\n                response={"field": field, "result": wireless.get(field) if isinstance(wireless, Mapping) else None},\n            )\n'''
new_helper = '''    @staticmethod\n    def _require_wps_action_ok(response: Mapping[str, Any], field: str) -> None:\n        # Physical ACIY.3 evidence shows action-specific response envelopes.\n        # PBC was observed nested under `wireless`, while Cancel returned the\n        # result directly at the top level. Accept only these two evidenced\n        # envelope locations; the actual action result must still be exactly OK.\n        result = response.get(field)\n        envelope = "top_level"\n        if result is None:\n            wireless = response.get("wireless")\n            if isinstance(wireless, Mapping):\n                result = wireless.get(field)\n                envelope = "wireless"\n        if result != "OK":\n            raise APIError(\n                f"WPS action did not return {field}=OK",\n                method_id="wireless/WPS_ACTION",\n                response={"field": field, "result": result, "envelope": envelope},\n            )\n'''
if old_helper not in wifi:
    raise SystemExit("current WPS helper block not found")
wifi = wifi.replace(old_helper, new_helper, 1)
WIFI.write_text(wifi, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
old_test = '''def test_wps_action_helpers_use_verified_contracts():\n    client, session = authenticated_client(\n        {"wireless": {"wps_call_pbc_result": "OK"}},\n        {"wireless": {"wps_call_cancel_result": "OK"}},\n        {"wireless": {"wps_call_pin_result": "OK"}},\n    )\n\n    assert client.wifi.call_wps_pbc()["wireless"]["wps_call_pbc_result"] == "OK"\n    assert client.wifi.call_wps_cancel()["wireless"]["wps_call_cancel_result"] == "OK"\n    assert client.wifi.call_wps_pin("12345670")["wireless"]["wps_call_pin_result"] == "OK"\n'''
new_test = '''def test_wps_action_helpers_use_verified_contracts():\n    client, session = authenticated_client(\n        {"wireless": {"wps_call_pbc_result": "OK"}},\n        {"wps_call_cancel_result": "OK"},\n        {"wireless": {"wps_call_pin_result": "OK"}},\n    )\n\n    assert client.wifi.call_wps_pbc()["wireless"]["wps_call_pbc_result"] == "OK"\n    assert client.wifi.call_wps_cancel()["wps_call_cancel_result"] == "OK"\n    assert client.wifi.call_wps_pin("12345670")["wireless"]["wps_call_pin_result"] == "OK"\n'''
if old_test not in tests:
    raise SystemExit("current WPS action test block not found")
tests = tests.replace(old_test, new_test, 1)

extra = '''\n\ndef test_wps_action_helpers_accept_both_evidenced_envelopes():\n    client, _ = authenticated_client(\n        {"wps_call_pbc_result": "OK"},\n        {"wireless": {"wps_call_cancel_result": "OK"}},\n    )\n    assert client.wifi.call_wps_pbc()["wps_call_pbc_result"] == "OK"\n    assert client.wifi.call_wps_cancel()["wireless"]["wps_call_cancel_result"] == "OK"\n'''
if "test_wps_action_helpers_accept_both_evidenced_envelopes" not in tests:
    tests += extra
TESTS.write_text(tests, encoding="utf-8")

integration = INTEGRATION.read_text(encoding="utf-8")
old_body = '''            pbc = router.wifi.call_wps_pbc()\n            assert pbc.get("wireless", {}).get("wps_call_pbc_result") == "OK"\n            cancel = router.wifi.call_wps_cancel()\n            assert cancel.get("wireless", {}).get("wps_call_cancel_result") == "OK"\n\n            pin = router.wifi.call_wps_pin("12345670")\n            assert pin.get("wireless", {}).get("wps_call_pin_result") == "OK"\n            cancel2 = router.wifi.call_wps_cancel()\n            assert cancel2.get("wireless", {}).get("wps_call_cancel_result") == "OK"\n'''
new_body = '''            def action_result(response: dict, field: str) -> tuple[str | None, str]:\n                if field in response:\n                    return response.get(field), "top_level"\n                wireless = response.get("wireless")\n                if isinstance(wireless, dict):\n                    return wireless.get(field), "wireless"\n                return None, "missing"\n\n            pbc = router.wifi.call_wps_pbc()\n            pbc_result, pbc_shape = action_result(pbc, "wps_call_pbc_result")\n            print(f"WPS_ACTION_SHAPE pbc={pbc_shape} result={pbc_result}")\n            assert pbc_result == "OK"\n\n            cancel = router.wifi.call_wps_cancel()\n            cancel_result, cancel_shape = action_result(cancel, "wps_call_cancel_result")\n            print(f"WPS_ACTION_SHAPE cancel_after_pbc={cancel_shape} result={cancel_result}")\n            assert cancel_result == "OK"\n\n            pin = router.wifi.call_wps_pin("12345670")\n            pin_result, pin_shape = action_result(pin, "wps_call_pin_result")\n            print(f"WPS_ACTION_SHAPE pin={pin_shape} result={pin_result}")\n            assert pin_result == "OK"\n\n            cancel2 = router.wifi.call_wps_cancel()\n            cancel2_result, cancel2_shape = action_result(cancel2, "wps_call_cancel_result")\n            print(f"WPS_ACTION_SHAPE cancel_after_pin={cancel2_shape} result={cancel2_result}")\n            assert cancel2_result == "OK"\n'''
if old_body not in integration:
    raise SystemExit("current physical WPS body not found")
integration = integration.replace(old_body, new_body, 1)
INTEGRATION.write_text(integration, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
anchor = "### Fixed\n\n"
entry = "- fixed WPS action response handling after physical ACIY.3 evidence showed `wifi_call_wps_cancel` returning a flat top-level `wps_call_cancel_result` while PBC returned its result under `wireless`; helpers now accept either evidenced envelope but still require the action result to be exactly `OK`\n"
if entry not in changelog:
    if anchor in changelog:
        changelog = changelog.replace(anchor, anchor + entry, 1)
    else:
        changelog += "\n### Fixed\n\n" + entry
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Fixed WPS action envelope handling and added physical shape tracing.")
