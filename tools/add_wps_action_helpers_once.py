# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

WIFI = Path("src/nr2301/namespaces/wifi.py")
TESTS = Path("tests/test_wifi_namespace.py")
INTEGRATION = Path("tests/integration/test_wps_actions.py")
CHANGELOG = Path("CHANGELOG.md")

wifi = WIFI.read_text(encoding="utf-8")

if "class WPSActionResponse" not in wifi:
    anchor = "class WPSStatus(TypedDict, total=False):\n"
    block = '''class WPSActionWireless(TypedDict, total=False):\n    wps_call_pbc_result: str\n    wps_call_pin_result: str\n    wps_call_cancel_result: str\n\n\nclass WPSActionResponse(TypedDict, total=False):\n    wireless: WPSActionWireless\n\n\n'''
    if anchor not in wifi:
        raise SystemExit("WPS TypedDict anchor not found")
    wifi = wifi.replace(anchor, block + anchor, 1)

if "    def call_wps_pbc(" not in wifi:
    anchor = "    def diagnostics(self, *, timeout: float | None = None) -> WiFiDiagnostics:\n"
    methods = '''    def call_wps_pbc(self, *, timeout: float | None = None) -> WPSActionResponse:\n        """Start the live-verified WPS push-button action.\n\n        This action does not auto-cancel. Consumers that only want to probe the\n        capability should call :meth:`call_wps_cancel` immediately afterwards.\n        """\n\n        response = self._client.call(\n            "wireless",\n            "wifi_call_wps_pbc",\n            timeout=timeout,\n        )\n        self._require_wps_action_ok(response, "wps_call_pbc_result")\n        return cast(WPSActionResponse, response)\n\n    def call_wps_pin(\n        self,\n        pin: str,\n        *,\n        timeout: float | None = None,\n    ) -> WPSActionResponse:\n        """Start the live-verified WPS PIN action using the supplied raw PIN.\n\n        The shipped frontend contract sends ``wps_enable=\"1\"`` together with\n        ``wps_pin``. The SDK intentionally does not invent a stricter PIN format\n        matrix than the evidence currently proves; firmware validation remains\n        authoritative.\n        """\n\n        if not isinstance(pin, str) or not pin:\n            raise ValueError("pin must be a non-empty string")\n        response = self._client.call(\n            "wireless",\n            "wifi_call_wps_pin",\n            data={"wps_enable": "1", "wps_pin": pin},\n            timeout=timeout,\n        )\n        self._require_wps_action_ok(response, "wps_call_pin_result")\n        return cast(WPSActionResponse, response)\n\n    def call_wps_cancel(self, *, timeout: float | None = None) -> WPSActionResponse:\n        """Cancel an active WPS PBC/PIN action and require the verified OK result."""\n\n        response = self._client.call(\n            "wireless",\n            "wifi_call_wps_cancel",\n            timeout=timeout,\n        )\n        self._require_wps_action_ok(response, "wps_call_cancel_result")\n        return cast(WPSActionResponse, response)\n\n'''
    if anchor not in wifi:
        raise SystemExit("WPS method insertion anchor not found")
    wifi = wifi.replace(anchor, methods + anchor, 1)

if "    def _require_wps_action_ok(" not in wifi:
    anchor = "    @staticmethod\n    def _extract_config("
    helper = '''    @staticmethod\n    def _require_wps_action_ok(response: Mapping[str, Any], field: str) -> None:\n        wireless = response.get("wireless")\n        if not isinstance(wireless, Mapping) or wireless.get(field) != "OK":\n            raise APIError(\n                f"WPS action did not return {field}=OK",\n                method_id="wireless/WPS_ACTION",\n                response={"field": field, "result": wireless.get(field) if isinstance(wireless, Mapping) else None},\n            )\n\n'''
    if anchor not in wifi:
        raise SystemExit("WPS helper insertion anchor not found")
    wifi = wifi.replace(anchor, helper + anchor, 1)

WIFI.write_text(wifi, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_wps_action_helpers_use_verified_contracts" not in tests:
    tests += '''\n\n\ndef test_wps_action_helpers_use_verified_contracts():\n    client, session = authenticated_client(\n        {"wireless": {"wps_call_pbc_result": "OK"}},\n        {"wireless": {"wps_call_cancel_result": "OK"}},\n        {"wireless": {"wps_call_pin_result": "OK"}},\n    )\n\n    assert client.wifi.call_wps_pbc()["wireless"]["wps_call_pbc_result"] == "OK"\n    assert client.wifi.call_wps_cancel()["wireless"]["wps_call_cancel_result"] == "OK"\n    assert client.wifi.call_wps_pin("12345670")["wireless"]["wps_call_pin_result"] == "OK"\n\n    assert session.calls[0][0] == "GET"\n    assert session.calls[0][2]["params"]["method"] == "wifi_call_wps_pbc"\n    assert session.calls[1][0] == "GET"\n    assert session.calls[1][2]["params"]["method"] == "wifi_call_wps_cancel"\n    assert session.calls[2][0] == "POST"\n    assert session.calls[2][2]["params"]["method"] == "wifi_call_wps_pin"\n    assert session.calls[2][2]["json"] == {"wps_enable": "1", "wps_pin": "12345670"}\n\n\ndef test_wps_pin_rejects_empty_value_before_network_access():\n    client, session = authenticated_client()\n    with pytest.raises(ValueError, match="pin must be a non-empty string"):\n        client.wifi.call_wps_pin("")\n    assert session.calls == []\n\n\ndef test_wps_action_rejects_non_ok_result():\n    client, _ = authenticated_client({"wireless": {"wps_call_pbc_result": "FAIL"}})\n    with pytest.raises(APIError, match="WPS action did not return"):\n        client.wifi.call_wps_pbc()\n'''
TESTS.write_text(tests, encoding="utf-8")

integration = '''# SPDX-License-Identifier: GPL-3.0-or-later\n\nfrom __future__ import annotations\n\nimport os\n\nimport pytest\n\nfrom nr2301 import NR2301Client\n\npytestmark = pytest.mark.integration\n\nif os.environ.get("NR2301_WRITE_INTEGRATION") != "1":\n    pytest.skip(\n        "physical WPS action test requires NR2301_WRITE_INTEGRATION=1",\n        allow_module_level=True,\n    )\n\n\ndef _client() -> NR2301Client:\n    password = os.environ.get("NR2301_PASSWORD")\n    if not password:\n        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")\n    router = NR2301Client(\n        os.environ.get("NR2301_URL", "http://zyxel.home"),\n        username=os.environ.get("NR2301_USERNAME", "admin"),\n        password=password,\n    )\n    router.login()\n    return router\n\n\ndef test_wps_pbc_pin_and_cancel_actions() -> None:\n    router = _client()\n    try:\n        original = router.wifi.wps()\n        original_enabled = str(original.get("wireless", {}).get("wps_enable")) == "1"\n        if not original_enabled:\n            router.wifi.set_wps_enabled(True, recovery_delay=0)\n        try:\n            pbc = router.wifi.call_wps_pbc()\n            assert pbc.get("wireless", {}).get("wps_call_pbc_result") == "OK"\n            cancel = router.wifi.call_wps_cancel()\n            assert cancel.get("wireless", {}).get("wps_call_cancel_result") == "OK"\n\n            pin = router.wifi.call_wps_pin("12345670")\n            assert pin.get("wireless", {}).get("wps_call_pin_result") == "OK"\n            cancel2 = router.wifi.call_wps_cancel()\n            assert cancel2.get("wireless", {}).get("wps_call_cancel_result") == "OK"\n        finally:\n            current = router.wifi.wps()\n            current_enabled = str(current.get("wireless", {}).get("wps_enable")) == "1"\n            if current_enabled != original_enabled:\n                router.wifi.set_wps_enabled(original_enabled, recovery_delay=0)\n    finally:\n        router.close()\n'''
INTEGRATION.write_text(integration, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
anchor = "### Added\n\n"
entry = "- added explicit `client.wifi.call_wps_pbc()`, `call_wps_pin()` and `call_wps_cancel()` wrappers for the already live-verified WPS action contracts, plus a reversible physical integration test that immediately cancels PBC/PIN and restores the original WPS-enable state\n"
if entry not in changelog:
    changelog = changelog.replace(anchor, anchor + entry, 1)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Added WPS action helpers, offline tests and physical integration test.")
