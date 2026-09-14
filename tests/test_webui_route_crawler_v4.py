# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "crawl_webui_routes_v4.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_v4_compiles() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")


def test_v4_removes_unbounded_page_content_capture() -> None:
    text = source()
    assert "rendered_html = page.content()" not in text
    assert "inner_html(timeout=timeout_ms)" in text
    assert "page.screenshot(" in text
    assert "timeout=5000" in text


def test_v4_isolated_route_pages_have_bounded_timeouts() -> None:
    text = source()
    assert "page = ctx.new_page()" in text
    assert "page.set_default_timeout(3000)" in text
    assert "page.set_default_navigation_timeout(10000)" in text
    assert "page.close(run_before_unload=False)" in text


def test_v4_checkpoints_and_reports_progress() -> None:
    text = source()
    assert "webui_routes_checkpoint.json" in text
    assert "WEBUI_ROUTE_PROGRESS =" in text
    assert "INTERRUPTED_BY_USER" in text
    assert "INTERRUPTED_PARTIAL" in text


def test_v4_keeps_source_driven_recursive_discovery() -> None:
    text = source()
    assert "OPENPAGE_RE" in text
    assert "extract_scripts" in text
    assert "discover_from_text" in text
    assert "layout_manager.js" in text


def test_v4_remains_read_only() -> None:
    text = source()
    assert "MUTATION_RE" in text
    assert "USB_RE" in text
    assert "route.abort()" in text
    assert "read-only source-driven WebUI crawler blocked mutation-like request" in text
