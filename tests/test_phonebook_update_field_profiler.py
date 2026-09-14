from __future__ import annotations

import runpy
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "explore_phonebook_update_fields.py"


def test_phonebook_update_field_profiler_compiles():
    source = SCRIPT.read_text(encoding="utf-8")
    compile(source, str(SCRIPT), "exec")


def test_phonebook_update_field_profiler_requires_explicit_write_gate(monkeypatch):
    monkeypatch.delenv("NR2301_WRITE_INTEGRATION", raising=False)
    namespace = runpy.run_path(str(SCRIPT))

    with pytest.raises(SystemExit, match="NR2301_WRITE_INTEGRATION=1"):
        namespace["_require_gate"]()


def test_phonebook_update_field_profiler_accepts_write_gate(monkeypatch):
    monkeypatch.setenv("NR2301_WRITE_INTEGRATION", "1")
    namespace = runpy.run_path(str(SCRIPT))
    namespace["_require_gate"]()
