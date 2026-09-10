from __future__ import annotations

import runpy
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "explore_phonebook_write_contracts.py"


def test_phonebook_write_profiler_compiles():
    source = SCRIPT.read_text(encoding="utf-8")
    compile(source, str(SCRIPT), "exec")


def test_phonebook_write_profiler_requires_explicit_write_gate(monkeypatch):
    monkeypatch.delenv("NR2301_WRITE_INTEGRATION", raising=False)
    namespace = runpy.run_path(str(SCRIPT))

    with pytest.raises(SystemExit, match="NR2301_WRITE_INTEGRATION=1"):
        namespace["_require_gate"]()


def test_phonebook_write_profiler_accepts_write_gate(monkeypatch):
    monkeypatch.setenv("NR2301_WRITE_INTEGRATION", "1")
    namespace = runpy.run_path(str(SCRIPT))
    namespace["_require_gate"]()


def test_phonebook_write_profiler_contains_update_semantics_and_prefix_cleanup():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "UPDATE_CONFIRMED_SEMANTICS" in source
    assert "COPY_ON_UPDATE" in source
    assert "_delete_synthetic_contacts" in source
    assert "NR2301_PHONEBOOK_REQUIRE_EMPTY" in source
