# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "cleanup_firewall_filter_residue.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_cleanup_harness_compiles() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")


def test_cleanup_harness_uses_all_slot_reads_and_known_test_values() -> None:
    source = _source()
    assert '{"ww_ip_filter": {"list": ["all"]}}' in source
    assert '{"ww_port_filter": {"list": ["all"]}}' in source
    assert 'TEST_IP = "203.0.113.77"' in source
    assert 'TEST_PORT = "65500:65500"' in source


def test_cleanup_harness_only_clears_matching_synthetic_values() -> None:
    source = _source()
    assert "if value == test_value" in source
    assert '{value_key: "0", "index": index}' in source
    assert "FIREWALL_FILTER_RESIDUE_CLEANUP = PASS" in source
