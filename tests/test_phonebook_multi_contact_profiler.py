from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROFILER = Path("examples/explore_phonebook_multi_contact_contracts.py")


def test_multi_contact_profiler_compiles():
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(PROFILER)],
        check=True,
    )


def test_multi_contact_profiler_is_hard_gated():
    env = os.environ.copy()
    env.pop("NR2301_WRITE_INTEGRATION", None)
    env.pop("NR2301_PHONEBOOK_REQUIRE_EMPTY", None)

    result = subprocess.run(
        [sys.executable, str(PROFILER)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "NR2301_WRITE_INTEGRATION=1" in combined


def test_comma_string_is_first_candidate_for_move_and_delete():
    source = PROFILER.read_text(encoding="utf-8")

    assert '("COMMA_STRING", f"{a},{b}")' in source
    assert source.index('(\"COMMA_STRING\", f\"{a},{b}\")') < source.index('(\"STRING_LIST\", [str(a), str(b)])')
    assert '"count": "2"' in source
