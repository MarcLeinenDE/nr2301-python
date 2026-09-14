# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "cleanup_port_trigger_webui_residue.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_recovery_compiles_and_is_write_gated() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")
    assert "NR2301_WRITE_INTEGRATION" in text
    assert "NR2301_PASSWORD is required" in text


def test_recovery_uses_two_step_webui_clear_semantics() -> None:
    text = source()
    assert 'data={"enable": 1, "items": slots}' in text
    assert 'data={"enable": 0}' in text
    assert 'PORT_TRIGGER_SYNTHETIC_CLEARED' in text
    assert 'PORT_TRIGGER_RECOVERY_RESTORED' in text


def test_recovery_guards_unrelated_rules() -> None:
    text = source()
    assert "recovery aborted: non-synthetic populated port-trigger rule present" in text
    assert 'TRIGGER_NAME = "SDK-PT-WEBUI"' in text
    assert 'TRIGGER_PORT = "65500"' in text
    assert 'TRIGGER_START = "65501"' in text
    assert 'TRIGGER_END = "65501"' in text


def test_recovery_excludes_unrelated_destructive_paths() -> None:
    text = source().lower()
    assert "switch_usb_mode" not in text
    assert "delete_dmz" not in text
    assert "factory" not in text
