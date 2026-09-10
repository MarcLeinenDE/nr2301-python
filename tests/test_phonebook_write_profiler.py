from __future__ import annotations

import runpy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "explore_phonebook_write_contracts.py"
FIELD_SCRIPT = ROOT / "examples" / "explore_phonebook_update_fields.py"


def test_phonebook_write_profiler_compiles():
    source = SCRIPT.read_text(encoding="utf-8")
    compile(source, str(SCRIPT), "exec")


def test_phonebook_update_field_profiler_compiles():
    source = FIELD_SCRIPT.read_text(encoding="utf-8")
    compile(source, str(FIELD_SCRIPT), "exec")


def test_phonebook_write_profiler_requires_explicit_write_gate(monkeypatch):
    monkeypatch.delenv("NR2301_WRITE_INTEGRATION", raising=False)
    namespace = runpy.run_path(str(SCRIPT))

    with pytest.raises(SystemExit, match="NR2301_WRITE_INTEGRATION=1"):
        namespace["_require_gate"]()


def test_phonebook_update_field_profiler_requires_explicit_write_gate(monkeypatch):
    monkeypatch.delenv("NR2301_WRITE_INTEGRATION", raising=False)
    namespace = runpy.run_path(str(FIELD_SCRIPT))

    with pytest.raises(SystemExit, match="NR2301_WRITE_INTEGRATION=1"):
        namespace["_require_gate"]()


def test_phonebook_write_profiler_accepts_write_gate(monkeypatch):
    monkeypatch.setenv("NR2301_WRITE_INTEGRATION", "1")
    namespace = runpy.run_path(str(SCRIPT))
    namespace["_require_gate"]()


def test_phonebook_update_field_profiler_accepts_write_gate(monkeypatch):
    monkeypatch.setenv("NR2301_WRITE_INTEGRATION", "1")
    namespace = runpy.run_path(str(FIELD_SCRIPT))
    namespace["_require_gate"]()


def test_phonebook_write_profiler_requires_index_cleanup_and_exact_restore():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "UPDATE_CONFIRMED_SEMANTICS" in source
    assert "COPY_ON_UPDATE" in source
    assert "_cleanup_new_indexes" in source
    assert "FINAL_INDEX_SET_MATCH" in source
    assert "FINAL_LOCAL_COUNT_MATCH" in source
    assert "phonebook baseline was not exactly restored" in source
    assert "NR2301_PHONEBOOK_REQUIRE_EMPTY" in source


def test_phonebook_update_field_profiler_uses_observed_baseline_and_index_cleanup():
    source = FIELD_SCRIPT.read_text(encoding="utf-8")
    assert "_cleanup_new_indexes" in source
    assert "observed_baseline" in source
    assert "CHANGED_FROM_BASELINE" in source
    assert "OTHERS_STABLE_FROM_OBSERVED_BASE" in source
    assert "FINAL_INDEX_SET_MATCH" in source
