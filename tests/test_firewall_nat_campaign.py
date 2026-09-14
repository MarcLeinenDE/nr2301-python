# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "explore_firewall_nat_campaign.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_firewall_nat_campaign_compiles() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")


def test_firewall_nat_campaign_requires_write_gate_and_exact_restore_checks() -> None:
    source = _source()
    assert 'NR2301_WRITE_INTEGRATION") != "1"' in source
    assert "_RESTORED = {restored}" in source
    assert "FIREWALL_NAT_FAILURE_COUNT" in source
    assert "FIREWALL_NAT_CAMPAIGN" in source


def test_firewall_nat_campaign_uses_synthetic_non_routable_test_values() -> None:
    source = _source()
    assert 'TEST_DOMAIN = "sdk-nr2301.invalid"' in source
    assert 'TEST_IP_FILTER_IP = "203.0.113.77"' in source
    assert 'TEST_PF_NAME_PREFIX = "SDK-PF-"' in source
    assert 'TEST_PT_NAME_PREFIX = "SDK-PT-"' in source


def test_firewall_nat_campaign_preserves_known_wire_types() -> None:
    source = _source()
    assert 'setter_data(str(target))' in source
    assert '"ww_port_filter": {"port_filter_disable": value}' in source
    assert '"ww_ip_filter": {"ip_filter_disable": value}' in source
    assert '"ww_upnp": {"upnp_enable": value}' in source


def test_firewall_nat_campaign_contains_all_batched_phases() -> None:
    source = _source()
    for phase in (
        "ADMIN_FROM_WAN",
        "PING_FROM_WAN",
        "VPN_PASSTHROUGH",
        "DMZ_DISABLE",
        "DMZ_EDIT",
        "UPNP",
        "IP_FILTER_SWITCH",
        "PORT_FILTER_SWITCH",
        "IP_FILTER_LIST",
        "PORT_FILTER_LIST",
        "URL_FILTER",
        "PORT_FORWARD",
        "PORT_TRIGGER",
    ):
        assert f'"{phase}"' in source
