# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "capture_firewall_webui_state.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_webui_snapshot_helper_compiles() -> None:
    source = _source()
    compile(source, str(SCRIPT), "exec")


def test_webui_snapshot_uses_complete_filter_reads() -> None:
    source = _source()
    assert '{"ww_ip_filter": {"list": ["all"]}}' in source
    assert '{"ww_port_filter": {"list": ["all"]}}' in source


def test_webui_snapshot_covers_quarantined_firewall_state() -> None:
    source = _source()
    for token in (
        '"dmz_info"',
        '"admin_from_wan"',
        '"ping_from_wan"',
        '"ip_filter_all"',
        '"port_filter_all"',
        '"port_trigger"',
    ):
        assert token in source


def test_webui_snapshot_does_not_mutate_usb_mode() -> None:
    source = _source().lower()
    assert "set_usb" not in source
    assert "usb_mode" not in source
