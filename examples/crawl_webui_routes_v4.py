# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
import html as html_lib
import json
import os
import re
import shutil
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from nr2301 import NR2301Client


OPENPAGE_RE = re.compile(
    r"""openPage\(\s*['\"]([^'\"]+\.html(?:\?[^'\"]*)?)['\"]""", re.I
)
HREF_RE = re.compile(
    r"""href\s*=\s*['\"](?!javascript:|#)([^'\"]+\.html(?:\?[^'\"]*)?)['\"]""",
    re.I,
)
WINDOW_OPEN_RE = re.compile(
    r"""window\.open\(\s*['\"]([^'\"]+\.html(?:\?[^'\"]*)?)['\"]""", re.I
)
SCRIPT_RE = re.compile(
    r"""<script[^>]+src\s*=\s*['\"]([^'\"]+\.js(?:\?[^'\"]*)?)['\"]""", re.I
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")

MUTATION_RE = re.compile(
    r"""(?is)(?:method=|[\"']method[\"']\s*:\s*[\"'])[^&\"']*"""
    r"""(?:set|edit|write|delete|remove|add|create|save|apply|update|clear|"""
    r"""switch|enable|disable|reboot|restart|reset|restore|upgrade|factory|usb)"""
)
USB_RE = re.compile(
    r"""(?is)(usb|usb_mode|management[_ -]?mode).{0,100}"""
    r"""(set|edit|write|switch|enable|disable)|"""
    r"""(set|edit|write|switch|enable|disable).{0,100}"""
    r"""(usb|usb_mode|management[_ -]?mode)"""
)

ROOT_SEEDS = (
    ("NETWORK STATUS", "html/home.html"),
    ("USER LIST", "html/user.html"),
    ("WI-FI SETTINGS", "html/wireless.html"),
    ("APP MODULE", "html/module.html"),
)


def require_read_gate() -> None:
    if not any(
        os.environ.get(name) == "1"
        for name in (
            "NR2301_INTEGRATION",
            "NR2301_WRITE_INTEGRATION",
            "NR2301_DESTRUCTIVE_INTEGRATION",
        )
    ):
        raise RuntimeError(
            "NR2301_INTEGRATION=1 (or a stronger physical-test gate) is required"
        )


def safe_slug(value: str, *, limit: int = 80) -> str:
    value = re.sub(r"\?.*$", "", value)
    value = re.sub(r"\s+", "_", value.strip().lower())
    value = re.sub(r"[^a-z0-9._/-]+", "", value).replace("/", "__")
    return (value or "route")[:limit]


def strip_tags(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_route(value: str, *, source_route: str | None = None) -> str | None:
    value = html_lib.unescape(value.strip())
    if not value or value.startswith(
        ("http://", "https://", "//", "javascript:", "#")
    ):
        return None
    parsed = urlsplit(value)
    path = parsed.path.replace("\\", "/")
    if not path.lower().endswith(".html"):
        return None
    if path.startswith("/"):
        path = path.lstrip("/")
    if not path.startswith("html/") and source_route and source_route.startswith("html/"):
        if "/" not in path:
            path = "html/" + path
    if path in {"login.html", "index.html"}:
        return None
    return path


def extract_routes(text: str, *, source_route: str | None = None) -> list[str]:
    out: list[str] = []
    for regex in (OPENPAGE_RE, HREF_RE, WINDOW_OPEN_RE):
        for match in regex.finditer(text):
            route = normalize_route(match.group(1), source_route=source_route)
            if route and route not in out:
                out.append(route)
    return out


def extract_scripts(text: str, *, source_url: str) -> list[str]:
    out: list[str] = []
    for match in SCRIPT_RE.finditer(text):
        url = urljoin(source_url, match.group(1))
        if url not in out:
            out.append(url)
    return out


def route_title_from_source(text: str) -> str | None:
    match = TITLE_RE.search(text)
    if match:
        title = strip_tags(match.group(1))
        if title:
            return title
    for pattern in (
        r"<h[1-4][^>]*>(.*?)</h[1-4]>",
        r"""class\s*=\s*['\"][^'\"]*(?:page-title|card-title|title)[^'\"]*['\"][^>]*>(.*?)</""",
    ):
        match = re.search(pattern, text, re.I | re.S)
        if match:
            title = strip_tags(match.group(1))
            if title:
                return title
    return None


def route_labels(text: str, *, source_route: str | None = None) -> dict[str, str]:
    labels: dict[str, str] = {}
    # Generic tagged element with openPage(...) in its attributes.
    for match in re.finditer(
        r"<(?P<tag>a|li|div|span|button)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
        text,
        re.I | re.S,
    ):
        attrs = match.group("attrs")
        inner = match.group("body")
        route_match = OPENPAGE_RE.search(attrs)
        if not route_match:
            href_match = HREF_RE.search(attrs)
            route_match = href_match
        if not route_match:
            continue
        route = normalize_route(route_match.group(1), source_route=source_route)
        label = strip_tags(inner)
        if route and label and len(label) <= 160:
            labels.setdefault(route, label)
    return labels


def launch_browser(playwright: Any, *, headless: bool) -> Any:
    for channel in ("chrome", "msedge"):
        try:
            return playwright.chromium.launch(channel=channel, headless=headless)
        except Exception:
            pass
    return playwright.chromium.launch(headless=headless)


class Recorder:
    def __init__(self, root: Path, origin: str) -> None:
        self.root = root
        self.origin = origin
        self.route_label = "bootstrap"
        self.events: list[dict[str, object]] = []
        self.blocked: list[dict[str, object]] = []

    def request(self, req: Any) -> None:
        if not req.url.startswith(self.origin):
            return
        self.events.append(
            {
                "kind": "request",
                "route": self.route_label,
                "time": datetime.now(timezone.utc).isoformat(),
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
            }
        )

    def response(self, resp: Any) -> None:
        if resp.url.startswith(self.origin):
            self.events.append(
                {
                    "kind": "response",
                    "route": self.route_label,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "status": resp.status,
                    "url": resp.url,
                }
            )

    def route(self, route: Any, req: Any) -> None:
        if not req.url.startswith(self.origin):
            route.continue_()
            return
        probe = f"{req.url}\n{req.post_data or ''}"
        method = req.method.upper()
        blocked = method not in {"GET", "HEAD", "OPTIONS"} and (
            MUTATION_RE.search(probe) or USB_RE.search(probe)
        )
        if blocked:
            item = {
                "time": datetime.now(timezone.utc).isoformat(),
                "route": self.route_label,
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
                "reason": (
                    "read-only source-driven WebUI crawler blocked mutation-like request"
                ),
            }
            self.blocked.append(item)
            self.events.append({"kind": "blocked", **item})
            route.abort()
        else:
            route.continue_()

    def save(self) -> None:
        (self.root / "webui_route_network.json").write_text(
            json.dumps(self.events, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        (self.root / "webui_route_blocked_requests.json").write_text(
            json.dumps(self.blocked, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )


def fetch_text(session: Any, url: str) -> tuple[int | None, str, str]:
    try:
        response = session.get(url, timeout=10.0)
        content_type = response.headers.get("content-type", "")
        if len(response.content) > 3_000_000:
            return response.status_code, content_type, ""
        response.encoding = response.encoding or "utf-8"
        return response.status_code, content_type, response.text
    except Exception as exc:
        return None, "", f"FETCH_ERROR:{type(exc).__name__}:{exc}"


def safe_locator_text(page: Any, selector: str, *, timeout_ms: int) -> str:
    try:
        loc = page.locator(selector).first
        if loc.count():
            return loc.inner_text(timeout=timeout_ms)
    except Exception:
        pass
    return ""


def safe_locator_html(page: Any, selector: str, *, timeout_ms: int) -> str:
    # Deliberately avoid page.content(): it can block indefinitely while the
    # NR2301 shell is replacing its dynamic content during navigation.
    try:
        loc = page.locator(selector).first
        if loc.count():
            return loc.inner_html(timeout=timeout_ms)
    except Exception:
        pass
    return ""


def settle_bounded(page: Any) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=1800)
    except Exception:
        pass
    time.sleep(0.35)


def browser_open_route(page: Any, base: str, route: str) -> tuple[bool, str]:
    try:
        page.goto(base, wait_until="domcontentloaded", timeout=10000)
        settle_bounded(page)
        if route.startswith("html/"):
            # Schedule the WebUI's own route loader asynchronously so evaluate()
            # itself cannot wait on an internal synchronous/long-running path.
            result = page.evaluate(
                """route => {
                    if (typeof openPage !== 'function') return false;
                    setTimeout(() => {
                      try { openPage(route); } catch (_) {}
                    }, 0);
                    return true;
                }""",
                route,
            )
            if result is not True:
                return False, "openPage-unavailable"
        else:
            page.goto(
                urljoin(base + "/", route),
                wait_until="domcontentloaded",
                timeout=10000,
            )
        settle_bounded(page)
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"


def capture_browser_state(
    page: Any,
    root: Path,
    index: int,
    route: str,
) -> dict[str, object]:
    dirname = f"{index:03d}_{safe_slug(route)}"
    state_dir = root / "routes" / dirname
    state_dir.mkdir(parents=True, exist_ok=True)

    screenshot_rel = f"routes/{dirname}/page.png"
    html_rel = f"routes/{dirname}/rendered_inner.html"
    text_rel = f"routes/{dirname}/visible.txt"

    errors: list[str] = []

    body_text = safe_locator_text(page, "body", timeout_ms=2500)
    main_text = safe_locator_text(page, ".main-content", timeout_ms=1800)
    rendered_html = safe_locator_html(page, "html", timeout_ms=2500)

    try:
        page.screenshot(
            path=str(root / screenshot_rel),
            full_page=True,
            timeout=5000,
        )
        screenshot_error = None
    except Exception as exc:
        screenshot_error = f"{type(exc).__name__}:{exc}"
        errors.append("screenshot:" + screenshot_error)

    heading = ""
    for selector in (
        ".main-content h1",
        ".main-content h2",
        ".main-content h3",
        ".main-content h4",
        ".main-content .title",
        ".main-content legend",
    ):
        value = safe_locator_text(page, selector, timeout_ms=800)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            heading = value
            break

    try:
        title = safe_locator_text(page, "title", timeout_ms=800)
    except Exception:
        title = ""

    (root / html_rel).write_text(
        rendered_html, encoding="utf-8", errors="replace"
    )
    (root / text_rel).write_text(
        body_text, encoding="utf-8", errors="replace"
    )

    return {
        "route": route,
        "browser_url": page.url,
        "document_title": title,
        "heading": heading,
        "main_text": main_text,
        "screenshot": screenshot_rel if screenshot_error is None else None,
        "rendered_html": html_rel,
        "visible_text": text_rel,
        "screenshot_error": screenshot_error,
        "capture_errors": errors,
        "rendered_routes": extract_routes(rendered_html, source_route=route),
    }


def shortest_paths(
    edges: dict[str, set[str]],
    labels: dict[tuple[str, str], str],
) -> dict[str, list[str]]:
    root = "__root__"
    queue: deque[str] = deque([root])
    paths: dict[str, list[str]] = {root: []}
    while queue:
        parent = queue.popleft()
        for child in sorted(edges.get(parent, set())):
            if child in paths:
                continue
            label = labels.get((parent, child)) or child
            paths[child] = paths[parent] + [label]
            queue.append(child)
    return paths


def save_checkpoint(
    root: Path,
    *,
    route_meta: dict[str, dict[str, object]],
    edges: dict[str, set[str]],
    labels: dict[tuple[str, str], str],
    queue: deque[str],
    blocked_requests: int,
) -> None:
    edge_rows = [
        {
            "parent": parent,
            "child": child,
            "label": labels.get((parent, child), ""),
        }
        for parent in sorted(edges)
        for child in sorted(edges[parent])
    ]
    checkpoint = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "routes": route_meta,
        "edges": edge_rows,
        "queue_remaining": list(queue),
        "blocked_request_count": blocked_requests,
    }
    (root / "webui_routes_checkpoint.json").write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def write_final_outputs(
    root: Path,
    *,
    base: str,
    route_meta: dict[str, dict[str, object]],
    edges: dict[str, set[str]],
    labels: dict[tuple[str, str], str],
    queue: deque[str],
    recorder: Recorder,
    interrupted: bool,
) -> dict[str, object]:
    recorder.save()
    paths = shortest_paths(edges, labels)
    edge_rows: list[dict[str, str]] = []
    for parent in sorted(edges):
        for child in sorted(edges[parent]):
            edge_rows.append(
                {
                    "parent": parent,
                    "child": child,
                    "label": labels.get((parent, child), ""),
                }
            )

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "routes": route_meta,
        "edges": edge_rows,
        "shortest_menu_paths": paths,
        "blocked_request_count": len(recorder.blocked),
        "queue_remaining": list(queue),
        "interrupted": interrupted,
    }
    (root / "webui_routes.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    with (root / "webui_route_edges.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["parent", "child", "label"]
        )
        writer.writeheader()
        writer.writerows(edge_rows)

    lines = [
        "# NR2301 WebUI route inventory",
        "",
        "Source-driven read-only inventory from the physical router.",
        "Raw screenshots and HTML may contain local device values and stay private.",
        "",
        "| # | Route | Menu path | Source | Browser | Screenshot |",
        "|---:|---|---|---:|---|---|",
    ]
    for route, meta in sorted(
        route_meta.items(), key=lambda kv: int(kv[1]["index"])
    ):
        path = " → ".join(paths.get(route, [route]))
        browser = meta.get("browser") or {}
        shot = browser.get("screenshot", "") if isinstance(browser, dict) else ""
        lines.append(
            f"| {meta['index']} | `{route}` | {path.replace('|', '/')} | "
            f"{meta.get('source_status')} | "
            f"{'OK' if meta.get('browser_ok') else meta.get('browser_reason')} | "
            f"`{shot or ''}` |"
        )
    lines.append("")
    (root / "WEBUI_ROUTE_MAP.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    summary: dict[str, object] = {
        "routes": len(route_meta),
        "browser_ok": sum(
            1 for value in route_meta.values() if value.get("browser_ok")
        ),
        "source_ok": sum(
            1
            for value in route_meta.values()
            if value.get("source_status") == 200
        ),
        "edges": len(edge_rows),
        "blocked_requests": len(recorder.blocked),
        "queue_remaining": len(queue),
        "completed": not queue and not interrupted,
        "interrupted": interrupted,
        "evidence_dir": str(root),
    }
    (root / "webui_route_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    require_read_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            r"Install once: .\.venv\Scripts\python.exe -m pip install playwright"
        ) from exc

    base = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    username = os.environ.get("NR2301_USERNAME", "admin")
    max_routes = int(os.environ.get("NR2301_WEBUI_MAX_ROUTES", "220"))
    headless = os.environ.get("NR2301_WEBUI_HEADLESS", "1") != "0"
    root = Path(
        os.environ.get(
            "NR2301_WEBUI_ROUTE_DIR",
            f"webui_routes_v4_{datetime.now():%Y%m%d-%H%M%S}",
        )
    )
    (root / "routes").mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)

    parsed = urlsplit(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    recorder = Recorder(root, origin)
    edges: dict[str, set[str]] = defaultdict(set)
    labels: dict[tuple[str, str], str] = {}
    route_meta: dict[str, dict[str, object]] = {}
    discovered: deque[str] = deque()
    queued: set[str] = set()
    fetched_scripts: set[str] = set()

    for label, route in ROOT_SEEDS:
        edges["__root__"].add(route)
        labels[("__root__", route)] = label
        discovered.append(route)
        queued.add(route)

    interrupted = False

    with NR2301Client(
        base, username=username, password=password, timeout=10.0
    ) as client:
        client.login()
        if not client.session_id:
            raise RuntimeError("SDK login returned no CGISID")

        def discover_from_text(
            text: str,
            *,
            parent: str,
            source_route: str | None,
        ) -> None:
            child_labels = route_labels(text, source_route=source_route)
            for child in extract_routes(text, source_route=source_route):
                edges[parent].add(child)
                if child in child_labels:
                    labels[(parent, child)] = child_labels[child]
                if child not in queued:
                    queued.add(child)
                    discovered.append(child)

        # Root and layout manager are known route registries.
        bootstrap_urls = [
            (base + "/", "__root__", None, "root.html"),
            (
                urljoin(base + "/", "js/base/layout_manager.js"),
                "__root__",
                None,
                "layout_manager.js",
            ),
        ]
        for url, parent, source_route, name in bootstrap_urls:
            status, ctype, text = fetch_text(client.transport.session, url)
            (root / "sources" / name).write_text(
                text, encoding="utf-8", errors="replace"
            )
            discover_from_text(
                text, parent=parent, source_route=source_route
            )

        with sync_playwright() as p:
            browser = launch_browser(p, headless=headless)
            ctx = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1440, "height": 1100},
            )
            ctx.add_cookies(
                [{"name": "CGISID", "value": client.session_id, "url": base}]
            )
            ctx.route("**/*", recorder.route)
            ctx.on("request", recorder.request)
            ctx.on("response", recorder.response)

            index = 0
            try:
                while discovered and index < max_routes:
                    route = discovered.popleft()
                    index += 1
                    recorder.route_label = route
                    source_url = urljoin(base + "/", route)
                    status, ctype, source = fetch_text(
                        client.transport.session, source_url
                    )
                    source_file = (
                        root
                        / "sources"
                        / f"{index:03d}_{safe_slug(route)}.html"
                    )
                    source_file.write_text(
                        source, encoding="utf-8", errors="replace"
                    )

                    discover_from_text(
                        source, parent=route, source_route=route
                    )

                    # Scan page-specific JS too; many routes live only there.
                    script_files: list[str] = []
                    for script_url in extract_scripts(
                        source, source_url=source_url
                    ):
                        if script_url in fetched_scripts:
                            continue
                        fetched_scripts.add(script_url)
                        s_status, s_ctype, script_text = fetch_text(
                            client.transport.session, script_url
                        )
                        script_name = (
                            f"{len(fetched_scripts):03d}_"
                            f"{safe_slug(urlsplit(script_url).path)}.js"
                        )
                        script_path = root / "scripts" / script_name
                        script_path.write_text(
                            script_text,
                            encoding="utf-8",
                            errors="replace",
                        )
                        script_files.append(
                            str(script_path.relative_to(root)).replace("\\", "/")
                        )
                        if s_status == 200:
                            discover_from_text(
                                script_text,
                                parent=route,
                                source_route=route,
                            )

                    page = ctx.new_page()
                    page.set_default_timeout(3000)
                    page.set_default_navigation_timeout(10000)
                    page.on("dialog", lambda dialog: dialog.dismiss())

                    ok, reason = browser_open_route(page, base, route)
                    browser_state: dict[str, object] | None = None
                    if ok:
                        browser_state = capture_browser_state(
                            page, root, index, route
                        )
                        for child in browser_state["rendered_routes"]:
                            if not isinstance(child, str):
                                continue
                            edges[route].add(child)
                            if child not in queued:
                                queued.add(child)
                                discovered.append(child)
                    try:
                        page.close(run_before_unload=False)
                    except Exception:
                        pass

                    route_meta[route] = {
                        "index": index,
                        "source_url": source_url,
                        "source_status": status,
                        "source_content_type": ctype,
                        "source_file": str(
                            source_file.relative_to(root)
                        ).replace("\\", "/"),
                        "source_title": route_title_from_source(source),
                        "script_files": script_files,
                        "browser_ok": ok,
                        "browser_reason": reason,
                        "browser": browser_state,
                    }

                    save_checkpoint(
                        root,
                        route_meta=route_meta,
                        edges=edges,
                        labels=labels,
                        queue=discovered,
                        blocked_requests=len(recorder.blocked),
                    )
                    print(
                        "WEBUI_ROUTE_PROGRESS = "
                        + json.dumps(
                            {
                                "index": index,
                                "route": route,
                                "source": status,
                                "browser": "OK" if ok else reason,
                                "discovered_total": len(queued),
                                "queue_remaining": len(discovered),
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
            except KeyboardInterrupt:
                interrupted = True
                print(
                    "WEBUI_ROUTE_CRAWL = INTERRUPTED_BY_USER; "
                    "writing partial evidence",
                    flush=True,
                )
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    summary = write_final_outputs(
        root,
        base=base,
        route_meta=route_meta,
        edges=edges,
        labels=labels,
        queue=discovered,
        recorder=recorder,
        interrupted=interrupted,
    )
    zip_path = shutil.make_archive(str(root), "zip", root_dir=root)
    print(
        "WEBUI_ROUTE_SUMMARY = "
        + json.dumps(summary, sort_keys=True),
        flush=True,
    )
    print(f"WEBUI_ROUTE_ZIP = {zip_path}", flush=True)
    if interrupted:
        status = "INTERRUPTED_PARTIAL"
    elif summary["completed"]:
        status = "COMPLETE"
    else:
        status = "BOUNDED_PARTIAL"
    print(f"WEBUI_ROUTE_CRAWL = {status}", flush=True)


if __name__ == "__main__":
    main()
