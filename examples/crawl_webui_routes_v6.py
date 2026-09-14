# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Read-only NR2301 WebUI route crawler with method-aware POST filtering.

v6 keeps the v5 source-driven crawl and engineering-page hardening, but fixes
an over-broad mutation detector that treated read methods such as
``get_updated_status`` as writes merely because their names contained
``update``. Browser navigation is still read-only: only POST requests whose
API method names are recognizably getter/read/query/list/status/statistics
operations are allowed. Explicit setters/actions and unknown POST method
shapes are blocked.
"""

import json
import os
import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from typing import Any

import crawl_webui_routes_v5 as v5

base = v5.base


READ_METHOD_PATTERNS = (
    re.compile(r"^get", re.I),
    re.compile(r"^router_get", re.I),
    re.compile(r"^wifi_get", re.I),
    re.compile(r"^ww_read", re.I),
    re.compile(r"^stat_get", re.I),
    re.compile(r"^read(?:_|$)", re.I),
    re.compile(r"^query(?:_|$)", re.I),
    re.compile(r"^new_query$", re.I),
    re.compile(r"^(?:sms\.)?(?:get|query|list)(?:[._]|$)", re.I),
)

WRITE_METHOD_PATTERNS = (
    re.compile(r"^(?:set|write|edit|delete|remove|add|create|save|apply|clear)(?:[._]|$)", re.I),
    re.compile(r"^(?:switch|enable|disable|reboot|restart|reset|restore|upgrade|factory)(?:[._]|$)", re.I),
    re.compile(r"(?:^|[._])(?:set|write|edit|delete|remove|add|create|save|apply|clear)(?:[._]|$)", re.I),
)


def _normalized_method(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def method_is_read_only(value: str) -> bool:
    method = _normalized_method(value)
    if not method:
        return False
    if any(pattern.search(method) for pattern in WRITE_METHOD_PATTERNS):
        return False
    return any(pattern.search(method) for pattern in READ_METHOD_PATTERNS)


def extract_api_methods(req: Any) -> list[str]:
    methods: list[str] = []

    try:
        query = parse_qs(urlsplit(str(req.url)).query)
        methods.extend(str(x) for x in query.get("method", []) if str(x).strip())
    except Exception:
        pass

    post_data = getattr(req, "post_data", None)
    if post_data:
        try:
            payload = json.loads(post_data)
        except Exception:
            payload = None

        if isinstance(payload, dict):
            method = payload.get("method")
            if method:
                methods.append(str(method))
            requests = payload.get("requests")
            if isinstance(requests, list):
                for item in requests:
                    if isinstance(item, dict) and item.get("method"):
                        methods.append(str(item["method"]))

    seen: set[str] = set()
    unique: list[str] = []
    for method in methods:
        if method not in seen:
            seen.add(method)
            unique.append(method)
    return unique


def route_v6(self: Any, route: Any, req: Any) -> None:
    if not req.url.startswith(self.origin):
        route.continue_()
        return

    method = req.method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        route.continue_()
        return

    methods = extract_api_methods(req)
    allow_read = bool(methods) and all(method_is_read_only(name) for name in methods)

    if allow_read:
        route.continue_()
        return

    item = {
        "time": datetime.now().astimezone().isoformat(),
        "route": self.route_label,
        "method": req.method,
        "url": req.url,
        "post_data": req.post_data,
        "api_methods": methods,
        "reason": (
            "read-only WebUI crawler blocked non-read or unknown POST request"
        ),
    }
    self.blocked.append(item)
    self.events.append({"kind": "blocked", **item})
    route.abort()


base.Recorder.route = route_v6

# Give this run an unambiguous local evidence-directory name while preserving
# an explicit caller-provided directory if one was set.
os.environ.setdefault(
    "NR2301_WEBUI_ROUTE_DIR",
    f"webui_routes_v6_{datetime.now():%Y%m%d-%H%M%S}",
)


if __name__ == "__main__":
    base.main()
