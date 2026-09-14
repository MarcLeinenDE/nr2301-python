# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "crawl_webui_routes_v3.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def load_module():
    spec = importlib.util.spec_from_file_location("crawl_webui_routes_v3", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_crawler_compiles_and_is_read_gated() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")
    assert "NR2301_INTEGRATION" in text
    assert "NR2301_PASSWORD is required" in text


def test_route_crawler_uses_frontend_routes_as_source_of_truth() -> None:
    text = source()
    assert "OPENPAGE_RE" in text
    assert "HREF_RE" in text
    assert "WINDOW_OPEN_RE" in text
    assert "openPage(route)" in text
    assert "html/module.html" in text


def test_route_extraction_normalizes_child_pages() -> None:
    module = load_module()
    text = """
      <a onclick="openPage('firewall_ip.html')">IP Filter</a>
      <a href="firewall_dmz.html">DMZ</a>
      <script>window.open('firewall_nat.html', '_self')</script>
    """
    assert module.extract_routes(text, source_route="html/module.html") == [
        "html/firewall_ip.html",
        "html/firewall_dmz.html",
        "html/firewall_nat.html",
    ]


def test_route_crawler_does_not_click_configuration_controls() -> None:
    text = source()
    assert "page.evaluate" in text
    assert "openPage(route)" in text
    assert ".click(" not in text
    assert "MUTATION_RE" in text
    assert "USB_RE" in text
    assert "route.abort()" in text


def test_route_crawler_records_reusable_route_artifacts() -> None:
    text = source()
    for token in (
        "WEBUI_ROUTE_MAP.md",
        "webui_routes.json",
        "webui_route_edges.csv",
        "webui_route_network.json",
        "webui_route_blocked_requests.json",
        "webui_route_summary.json",
        "rendered.html",
        "visible.txt",
        "page.png",
        "shutil.make_archive",
    ):
        assert token in text


def test_route_crawler_has_expected_top_level_menu() -> None:
    module = load_module()
    assert module.ROOT_SEEDS == (
        ("NETWORK STATUS", "html/home.html"),
        ("USER LIST", "html/user.html"),
        ("WI-FI SETTINGS", "html/wireless.html"),
        ("APP MODULE", "html/module.html"),
    )
