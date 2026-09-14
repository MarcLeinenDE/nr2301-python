# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "crawl_webui_inventory_v2.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_v2_compiles_and_reuses_read_only_base_crawler() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")
    assert "import crawl_webui_inventory as base" in text
    assert "base.capture_state = capture_state" in text
    assert "base.main()" in text


def test_v2_retries_transient_none_dom_results() -> None:
    text = source()
    assert "attempts: int = 6" in text
    assert "isinstance(data, dict)" in text
    assert "unexpected-result" in text
    assert "playwright-fallback" in text


def test_v2_keeps_evidence_even_when_dom_inventory_fails() -> None:
    text = source()
    for token in (
        'page.locator("body").inner_text',
        "page.content()",
        "page.screenshot",
        "capture_warnings",
        "screenshot_diagnostic",
        '"candidates": []',
    ):
        assert token in text


def test_v2_never_assumes_candidate_shape() -> None:
    text = source()
    assert "isinstance(raw_candidates, list)" in text
    assert "isinstance(c, dict)" in text
    assert "normalized to empty list" in text
