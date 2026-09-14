# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "automate_firewall_webui_crawl_v2.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_v2_compiles_and_is_write_gated() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")
    assert 'NR2301_WRITE_INTEGRATION") != "1"' in source
    assert "NR2301_PASSWORD is required" in source


def test_v2_opens_real_dashboard_app_module_without_role_assumption() -> None:
    source = _source()
    assert '"APP MODULE"' in source
    assert "generic_click" in source
    assert "clickable ancestor" in source
    assert "getComputedStyle" in source


def test_v2_records_navigation_discovery_evidence() -> None:
    source = _source()
    assert "firewall_webui_v2_discovery.json" in source
    assert "body_text" in source
    assert "clickables" in source
    assert "page.screenshot" in source


def test_v2_delegates_mutations_to_usb_guarded_v1_harness() -> None:
    source = _source()
    assert "import automate_firewall_webui_crawl as base" in source
    assert "base.click_button = click_button_v2" in source
    assert "base.navigate = navigate_v2" in source
    assert "base.main()" in source
