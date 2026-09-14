# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "crawl_webui_routes_v5.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_v5_wrapper_compiles() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")


def test_v5_removes_locator_count_from_capture_helpers() -> None:
    text = source()
    assert ".count()" not in text
    assert "inner_text(timeout=timeout_ms)" in text
    assert "inner_html(timeout=timeout_ms)" in text


def test_v5_marks_engineering_routes_source_only() -> None:
    text = source()
    for route in (
        '"engineering.html"',
        '"html/engineering.html"',
        '"html/engineer_info.html"',
    ):
        assert route in text
    assert 'return False, "source-only-engineering-route"' in text


def test_v5_delegates_to_v4_main() -> None:
    text = source()
    assert "import crawl_webui_routes_v4 as base" in text
    assert "base.main()" in text
