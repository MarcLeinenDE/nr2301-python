# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "automate_firewall_webui_crawl.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_autopilot_compiles_and_is_write_gated() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")
    assert 'NR2301_WRITE_INTEGRATION") != "1"' in source
    assert "NR2301_PASSWORD is required" in source


def test_autopilot_reuses_sdk_session_for_browser() -> None:
    source = _source()
    assert "client.login()" in source
    assert "client.session_id" in source
    assert '"name": "CGISID"' in source
    assert "sync_playwright" in source


def test_autopilot_has_hard_usb_mutation_block() -> None:
    source = _source()
    assert "USB_RE" in source
    assert "USB/management-mode mutation blocked" in source
    assert "route.abort()" in source
    assert "usb_mutation_blocked" in source


def test_autopilot_covers_quarantined_firewall_contracts() -> None:
    source = _source()
    for item in (
        'results["admin_from_wan"]',
        'results["ping_from_wan"]',
        'results["dmz_clear"]',
        'results["ip_filter"]',
        'results["port_filter"]',
        'results["port_trigger"]',
    ):
        assert item in source
    assert 'TEST_IP = "203.0.113.77"' in source
    assert 'TEST_PORT = "65500"' in source
    assert 'TEST_TRIGGER = "SDK-PT-WEBUI"' in source


def test_autopilot_records_full_local_snapshots_and_network_evidence() -> None:
    source = _source()
    assert "from capture_firewall_webui_state import capture" in source
    assert "campaign_baseline" in source
    assert "campaign_final" in source
    assert "firewall_webui_autopilot_network.json" in source
    assert "firewall_webui_autopilot_summary.json" in source
    assert "FIREWALL_WEBUI_AUTOPILOT" in source
