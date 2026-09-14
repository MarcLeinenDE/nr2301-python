# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "explore_firewall_nat_round2.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_round2_compiles_and_is_write_gated() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")
    assert 'NR2301_WRITE_INTEGRATION") != "1"' in source
    assert "NR2301_PASSWORD is required" in source


def test_round2_retests_only_open_contracts() -> None:
    source = _source()
    for phase in (
        "ADMIN_FROM_WAN_INT",
        "PING_FROM_WAN_INT",
        "VPN_PASSTHROUGH_INT",
        "IP_FILTER_LIST_SENTINEL",
        "PORT_FILTER_LIST_SENTINEL",
    ):
        assert phase in source
    for already_confirmed in (
        '"DMZ_DISABLE"',
        '"UPNP"',
        '"PORT_FORWARD"',
        '"URL_FILTER"',
    ):
        assert already_confirmed not in source


def test_round2_uses_source_backed_filter_slot_sentinels() -> None:
    source = _source()
    assert "range(10)" in source
    assert 'empty: str = "0"' in source
    assert 'TEST_IP = "203.0.113.77"' in source
    assert 'TEST_PORT = "65500:65500"' in source
    assert 'disable_field: "0"' in source


def test_round2_tests_native_integer_hypotheses_before_mutation() -> None:
    source = _source()
    assert "INT_SAME_STATE_ACCEPTED" in source
    assert 'data={request_key: original}' in source
    assert 'data=original)' in source
    assert "VPN_INT_SAME_STATE_RESULT" in source


def test_round2_keeps_dmz_and_port_trigger_items_quarantined() -> None:
    source = _source()
    assert "DMZ quarantine requires dmz_disable='1'" in source
    assert "PORT_TRIGGER_ITEM_SCHEMA = QUARANTINED_FOR_WEBUI_CRAWL" in source
    assert "fw_edit_dmz_entry" not in source
    assert '"set_port_trigger"' not in source


def test_round2_reports_restore_and_summary_markers() -> None:
    source = _source()
    assert "_RESTORED = {restored}" in source
    assert "LIST_RESTORED" in source
    assert "SWITCH_RESTORED" in source
    assert "FIREWALL_NAT_ROUND2_FAILURE_COUNT" in source
    assert "FIREWALL_NAT_ROUND2" in source
