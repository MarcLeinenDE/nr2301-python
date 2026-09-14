# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import crawl_webui_inventory as base


def _fallback_dom_snapshot(page: Any, warnings: list[str]) -> dict[str, Any]:
    """Best-effort snapshot when the in-page inventory script cannot return a dict."""
    try:
        url = str(page.url or "")
    except Exception as exc:
        warnings.append(f"fallback-url:{type(exc).__name__}:{exc}")
        url = ""

    try:
        title = str(page.title() or "")
    except Exception as exc:
        warnings.append(f"fallback-title:{type(exc).__name__}:{exc}")
        title = ""

    try:
        body_text = str(page.locator("body").inner_text(timeout=5000) or "")
    except Exception as exc:
        warnings.append(f"fallback-body:{type(exc).__name__}:{exc}")
        body_text = ""

    try:
        html = str(page.content() or "")
    except Exception as exc:
        warnings.append(f"fallback-html:{type(exc).__name__}:{exc}")
        html = ""

    frames: list[dict[str, str]] = []
    try:
        for frame in page.frames:
            frames.append(
                {
                    "src": str(frame.url or ""),
                    "name": str(frame.name or ""),
                    "id": "",
                }
            )
    except Exception as exc:
        warnings.append(f"fallback-frames:{type(exc).__name__}:{exc}")

    return {
        "url": url,
        "title": title,
        "body_text": body_text,
        "html": html,
        "candidates": [],
        "frames": frames,
        "capture_warnings": warnings,
        "capture_mode": "playwright-fallback",
    }


def _evaluate_inventory(page: Any, *, attempts: int = 6) -> dict[str, Any]:
    warnings: list[str] = []

    for attempt in range(1, attempts + 1):
        base.settle(page, delay=0.45 if attempt == 1 else 0.75)
        try:
            data = page.evaluate(base.DOM_INVENTORY_JS)
        except Exception as exc:
            warnings.append(
                f"attempt-{attempt}:evaluate:{type(exc).__name__}:{exc}"
            )
            time.sleep(0.35 * attempt)
            continue

        if isinstance(data, dict):
            data = dict(data)
            data["capture_mode"] = "dom-inventory-js"
            if warnings:
                data["capture_warnings"] = warnings
            return data

        warnings.append(
            f"attempt-{attempt}:unexpected-result:{type(data).__name__}:{data!r}"
        )
        time.sleep(0.35 * attempt)

    return _fallback_dom_snapshot(page, warnings)


def capture_state(
    page: Any,
    root: Path,
    *,
    index: int,
    menu_path: list[dict[str, str]],
) -> dict[str, Any]:
    data = _evaluate_inventory(page)
    label = menu_path[-1]["text"] if menu_path else "home"
    dirname = f"{index:03d}_{base.safe_slug(label)}"
    state_dir = root / "states" / dirname
    state_dir.mkdir(parents=True, exist_ok=True)

    body_text = str(data.get("body_text") or "")
    html = str(data.pop("html", ""))
    screenshot_rel = f"states/{dirname}/page.png"
    html_rel = f"states/{dirname}/page.html"
    text_rel = f"states/{dirname}/page.txt"
    dom_rel = f"states/{dirname}/dom.json"

    screenshot_error: str | None = None
    try:
        page.screenshot(path=str(root / screenshot_rel), full_page=True, timeout=15000)
    except Exception as exc:
        screenshot_error = f"{type(exc).__name__}: {exc}"
        try:
            page.screenshot(path=str(root / screenshot_rel), full_page=False, timeout=5000)
            screenshot_error += " | viewport fallback succeeded"
        except Exception as fallback_exc:
            screenshot_error += (
                f" | viewport fallback failed: {type(fallback_exc).__name__}: "
                f"{fallback_exc}"
            )

    if screenshot_error:
        data["screenshot_diagnostic"] = screenshot_error

    (root / html_rel).write_text(html, encoding="utf-8", errors="replace")
    (root / text_rel).write_text(body_text, encoding="utf-8", errors="replace")
    (root / dom_rel).write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    raw_candidates = data.get("candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = []
        data.setdefault("capture_warnings", []).append(
            "candidates was not a list; normalized to empty list"
        )

    candidates = [
        c
        for c in raw_candidates
        if isinstance(c, dict) and base.candidate_is_navigation(c)
    ]
    candidates.sort(key=base.candidate_score)

    return {
        "index": index,
        "menu_path": [x["text"] for x in menu_path],
        "menu_specs": menu_path,
        "url": data.get("url"),
        "title": data.get("title"),
        "fingerprint": base.normalized_fingerprint(
            str(data.get("url") or ""), str(data.get("title") or ""), body_text
        ),
        "screenshot": screenshot_rel,
        "html": html_rel,
        "text": text_rel,
        "dom": dom_rel,
        "frames": data.get("frames", []),
        "candidates": candidates,
        "capture_mode": data.get("capture_mode"),
        "capture_warnings": data.get("capture_warnings", []),
    }


def main() -> None:
    # Keep the proven crawler and replace only the fragile state-capture seam.
    base.capture_state = capture_state
    base.main()


if __name__ == "__main__":
    main()
