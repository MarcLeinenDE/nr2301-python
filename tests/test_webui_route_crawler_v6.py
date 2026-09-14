# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SCRIPT = EXAMPLES / "crawl_webui_routes_v6.py"


def load_module():
    sys.path.insert(0, str(EXAMPLES))
    try:
        spec = importlib.util.spec_from_file_location("crawl_webui_routes_v6_test", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_v6_compiles() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    compile(text, str(SCRIPT), "exec")


def test_v6_allows_observed_read_only_methods() -> None:
    module = load_module()
    for method in (
        "router_get_work_mode",
        "get_sim_status",
        "wifi_get_basic_info",
        "sms.get_brief_info",
        "get_current_wan_info",
        "get_cell_info",
        "new_query",
        "get_ui_language",
        "get_extender_status",
        "get_package_status",
        "get_bat_info",
        "get_updated_status",
        "get_conn_clients_info",
        "sms.query",
        "sms.list_by_type",
        "getcontactbylocation",
        "router_get_dhcp_settings_comb",
        "ww_read_switch_mode_state",
        "ww_read_ip_filter",
        "ww_read_switch_port_mode_state",
        "ww_read_port_filter",
    ):
        assert module.method_is_read_only(method), method


def test_v6_rejects_write_or_unknown_methods() -> None:
    module = load_module()
    for method in (
        "set_admin_from_wan",
        "ww_write_ip_filter",
        "sms.delete",
        "delete_contact",
        "apply_settings",
        "reboot",
        "switch_usb_mode",
        "totally_unknown_action",
    ):
        assert not module.method_is_read_only(method), method


def test_v6_preserves_v5_source_only_engineering_routes() -> None:
    module = load_module()
    assert "engineering.html" in module.v5.SOURCE_ONLY_ROUTES
    assert "html/engineer_info.html" in module.v5.SOURCE_ONLY_ROUTES


def test_v6_uses_distinct_evidence_directory_prefix() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "webui_routes_v6_" in text
