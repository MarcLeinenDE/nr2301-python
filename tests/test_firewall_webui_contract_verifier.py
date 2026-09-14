# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "verify_firewall_webui_contracts.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_verifier_compiles_and_is_write_gated() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")
    assert 'NR2301_WRITE_INTEGRATION' in text
    assert 'NR2301_PASSWORD is required' in text


def test_verifier_uses_source_confirmed_nested_wan_shapes() -> None:
    text = source()
    assert 'data={outer: {field: value}}' in text
    assert 'outer="ping_from_wan"' in text
    assert 'field="ping_from_wan_enable"' in text
    assert 'outer="admin_from_wan"' in text
    assert 'field="admin_from_wan_enable"' in text


def test_verifier_uses_full_filter_reads_and_string_wire_indices() -> None:
    text = source()
    assert 'data={outer: {"list": ["all"]}}' in text
    assert '"index": str(i)' in text
    assert '{disable_field: value}' in text
    assert 'TEST_IP = "203.0.113.77"' in text
    assert 'TEST_PORT = "65500:65500"' in text


def test_verifier_uses_native_port_trigger_shape_and_restores() -> None:
    text = source()
    assert '"index": free_slot' in text
    assert '"trigger_port": TRIGGER_PORT' in text
    assert '"start_port": TRIGGER_START' in text
    assert '"end_port": TRIGGER_END' in text
    assert 'PORT_TRIGGER_RESTORED' in text


def test_verifier_excludes_usb_and_dmz_clear_guesses() -> None:
    text = source().lower()
    assert 'switch_usb_mode' not in text
    assert 'delete_dmz' not in text
    assert 'fw_add_dmz_entry' not in text


def test_verifier_checks_final_synthetic_residue() -> None:
    text = source()
    assert 'FINAL_SYNTHETIC_IP_PRESENT' in text
    assert 'FINAL_SYNTHETIC_PORT_PRESENT' in text
    assert 'FINAL_SYNTHETIC_TRIGGER_PRESENT' in text
