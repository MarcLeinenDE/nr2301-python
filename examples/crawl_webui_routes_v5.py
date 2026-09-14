# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Hardened wrapper for the source-driven NR2301 WebUI route crawler.

v5 keeps the v4 crawl/output format, but removes Playwright ``Locator.count()``
from the capture path and treats known engineering/diagnostic shell pages as
source-only evidence.  Those pages have repeatedly left Chromium in a state
where DOM inspection can block indefinitely even though their static HTML was
fetched successfully.
"""

import re
from typing import Any

import crawl_webui_routes_v4 as base


SOURCE_ONLY_ROUTES = {
    "engineering.html",
    "html/engineering.html",
    "html/engineer_info.html",
}


def safe_locator_text_v5(page: Any, selector: str, *, timeout_ms: int) -> str:
    """Read text without ``Locator.count()``, which may block indefinitely."""
    try:
        return page.locator(selector).first.inner_text(timeout=timeout_ms)
    except Exception:
        return ""


def safe_locator_html_v5(page: Any, selector: str, *, timeout_ms: int) -> str:
    """Read HTML without ``Locator.count()``, which may block indefinitely."""
    try:
        return page.locator(selector).first.inner_html(timeout=timeout_ms)
    except Exception:
        return ""


def browser_open_route_v5(page: Any, base_url: str, route: str) -> tuple[bool, str]:
    normalized = re.sub(r"[?#].*$", "", route.strip().lower())
    if normalized in SOURCE_ONLY_ROUTES:
        return False, "source-only-engineering-route"
    return _ORIGINAL_BROWSER_OPEN_ROUTE(page, base_url, route)


_ORIGINAL_BROWSER_OPEN_ROUTE = base.browser_open_route
base.safe_locator_text = safe_locator_text_v5
base.safe_locator_html = safe_locator_html_v5
base.browser_open_route = browser_open_route_v5


if __name__ == "__main__":
    base.main()
