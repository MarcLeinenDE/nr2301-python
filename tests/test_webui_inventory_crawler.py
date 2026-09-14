# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "crawl_webui_inventory.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_inventory_crawler_compiles_and_uses_read_gate() -> None:
    text = source()
    compile(text, str(SCRIPT), "exec")
    assert "NR2301_INTEGRATION" in text
    assert "NR2301_PASSWORD is required" in text


def test_inventory_crawler_is_read_only_and_blocks_mutation_like_requests() -> None:
    text = source()
    assert "MUTATION_RE" in text
    assert "DANGER_RE" in text
    assert "route.abort()" in text
    assert "read-only WebUI inventory crawler blocked mutation-like request" in text


def test_inventory_crawler_records_reusable_webui_artifacts() -> None:
    text = source()
    for token in (
        "webui_inventory.json",
        "WEBUI_TREE.md",
        "webui_menu_paths.csv",
        "webui_network.json",
        "webui_blocked_requests.json",
        "webui_assets_manifest.json",
        "page.png",
        "page.html",
        "page.txt",
        "dom.json",
    ):
        assert token in text


def test_inventory_crawler_discovers_computed_pointer_targets() -> None:
    text = source()
    assert "getComputedStyle(cur)" in text
    assert "s.cursor === 'pointer'" in text
    assert "interactiveAncestor" in text
    assert "cssPath" in text


def test_inventory_crawler_is_bounded_and_replayable() -> None:
    text = source()
    assert "NR2301_WEBUI_MAX_STATES" in text
    assert "NR2301_WEBUI_MAX_DEPTH" in text
    assert "NR2301_WEBUI_MAX_CANDIDATES" in text
    assert "replay_path" in text
    assert "seen_fingerprints" in text
    assert "queued_paths" in text


def test_inventory_crawler_archives_loaded_static_frontend_sources() -> None:
    text = source()
    assert "archive_static_assets" in text
    assert '{".html", ".js", ".css", ".json"}' in text
    assert '"/api.cgi" in url' in text
    assert "static_assets" in text


def test_inventory_crawler_produces_single_zip() -> None:
    text = source()
    assert "shutil.make_archive" in text
    assert "WEBUI_INVENTORY_ZIP =" in text
