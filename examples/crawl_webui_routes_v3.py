# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
import hashlib
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


OPENPAGE_RE = re.compile(r"openPage\(\s*['\"]([^'\"]+\.html(?:\?[^'\"]*)?)['\"]", re.I)
HREF_RE = re.compile(r"href\s*=\s*['\"](?!javascript:|#)([^'\"]+\.html(?:\?[^'\"]*)?)['\"]", re.I)
WINDOW_OPEN_RE = re.compile(r"window\.open\(\s*['\"]([^'\"]+\.html(?:\?[^'\"]*)?)['\"]", re.I)
SCRIPT_RE = re.compile(r"<script[^>]+src\s*=\s*['\"]([^'\"]+\.js(?:\?[^'\"]*)?)['\"]", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")

MUTATION_RE = re.compile(
    r"(?is)(?:method=|[\"']method[\"']\s*:\s*[\"'])[^&\"']*"
    r"(?:set|edit|write|delete|remove|add|create|save|apply|update|clear|"
    r"switch|enable|disable|reboot|restart|reset|restore|upgrade|factory|usb)"
)
USB_RE = re.compile(r"(?is)(usb|usb_mode|management[_ -]?mode).{0,100}(set|edit|write|switch|enable|disable)|"
                    r"(set|edit|write|switch|enable|disable).{0,100}(usb|usb_mode|management[_ -]?mode)")

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
    if not value or value.startswith(("http://", "https://", "//", "javascript:", "#")):
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
        r"class\s*=\s*['\"][^'\"]*(?:page-title|card-title|title)[^'\"]*['\"][^>]*>(.*?)</",
    ):
        match = re.search(pattern, text, re.I | re.S)
        if match:
            title = strip_tags(match.group(1))
            if title:
                return title
    return None


def route_labels(text: str, *, source_route: str | None = None) -> dict[str, str]:
    labels: dict[str, str] = {}
    # Capture ordinary anchors whose onclick contains openPage(...).
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", text, re.I | re.S):
        attrs, inner = match.group(1), match.group(2)
        route_match = OPENPAGE_RE.search(attrs)
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


def settle(page: Any, delay: float = 1.0) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=2500)
    except Exception:
        pass
    time.sleep(delay)


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
        self.events.append({
            "kind": "request",
            "route": self.route_label,
            "time": datetime.now(timezone.utc).isoformat(),
            "method": req.method,
            "url": req.url,
            "post_data": req.post_data,
        })

    def response(self, resp: Any) -> None:
        if resp.url.startswith(self.origin):
            self.events.append({
                "kind": "response",
                "route": self.route_label,
                "time": datetime.now(timezone.utc).isoformat(),
                "status": resp.status,
                "url": resp.url,
            })

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
                "reason": "read-only source-driven WebUI crawler blocked mutation-like request",
            }
            self.blocked.append(item)
            self.events.append({"kind": "blocked", **item})
            route.abort()
        else:
            route.continue_()

    def save(self) -> None:
        (self.root / "webui_route_network.json").write_text(
            json.dumps(self.events, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        (self.root / "webui_route_blocked_requests.json").write_text(
            json.dumps(self.blocked, indent=2, sort_keys=True, default=str), encoding="utf-8"
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


def browser_open_route(page: Any, base: str, route: str) -> tuple[bool, str]:
    try:
        page.goto(base, wait_until="domcontentloaded", timeout=15000)
        settle(page, 0.5)
        if route == "engineering.html":
            page.goto(urljoin(base + "/", route), wait_until="domcontentloaded", timeout=15000)
        else:
            result = page.evaluate(
                "route => { if (typeof openPage !== 'function') return false; openPage(route); return true; }",
                route,
            )
            if result is not True:
                return False, "openPage-unavailable"
        settle(page, 1.0)
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"


def capture_browser_state(page: Any, root: Path, index: int, route: str) -> dict[str, object]:
    dirname = f"{index:03d}_{safe_slug(route)}"
    state_dir = root / "routes" / dirname
    state_dir.mkdir(parents=True, exist_ok=True)
    screenshot_rel = f"routes/{dirname}/page.png"
    html_rel = f"routes/{dirname}/rendered.html"
    text_rel = f"routes/{dirname}/visible.txt"

    try:
        rendered_html = page.content()
    except Exception:
        rendered_html = ""
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""
    try:
        main_text = page.locator(".main-content").inner_text(timeout=2000)
    except Exception:
        main_text = ""
    try:
        page.screenshot(path=str(root / screenshot_rel), full_page=True)
        screenshot_error = None
    except Exception as exc:
        screenshot_error = f"{type(exc).__name__}:{exc}"

    (root / html_rel).write_text(rendered_html, encoding="utf-8", errors="replace")
    (root / text_rel).write_text(body_text, encoding="utf-8", errors="replace")

    heading = ""
    for selector in (".main-content h1", ".main-content h2", ".main-content h3", ".main-content h4", ".main-content .title", ".main-content legend"):
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                heading = re.sub(r"\s+", " ", loc.inner_text()).strip()
                if heading:
                    break
        except Exception:
            pass

    digest = hashlib.sha256((route + "\n" + main_text).encode("utf-8", errors="replace")).hexdigest()
    return {
        "route": route,
        "browser_url": page.url,
        "document_title": page.title(),
        "heading": heading,
        "main_text": main_text,
        "fingerprint": digest,
        "screenshot": screenshot_rel,
        "rendered_html": html_rel,
        "visible_text": text_rel,
        "screenshot_error": screenshot_error,
        "rendered_routes": extract_routes(rendered_html, source_route=route),
    }


def shortest_paths(edges: dict[str, set[str]], labels: dict[tuple[str, str], str]) -> dict[str, list[str]]:
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


def main() -> None:
    require_read_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(r"Install once: .\.venv\Scripts\python.exe -m pip install playwright") from exc

    base = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    username = os.environ.get("NR2301_USERNAME", "admin")
    max_routes = int(os.environ.get("NR2301_WEBUI_MAX_ROUTES", "220"))
    headless = os.environ.get("NR2301_WEBUI_HEADLESS", "1") != "0"
    root = Path(os.environ.get("NR2301_WEBUI_ROUTE_DIR", f"webui_routes_{datetime.now():%Y%m%d-%H%M%S}"))
    (root / "routes").mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(parents=True, exist_ok=True)

    parsed = urlsplit(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    recorder = Recorder(root, origin)
    edges: dict[str, set[str]] = defaultdict(set)
    labels: dict[tuple[str, str], str] = {}
    route_meta: dict[str, dict[str, object]] = {}
    discovered: deque[str] = deque()
    queued: set[str] = set()

    for label, route in ROOT_SEEDS:
        edges["__root__"].add(route)
        labels[("__root__", route)] = label
        discovered.append(route)
        queued.add(route)

    with NR2301Client(base, username=username, password=password, timeout=10.0) as client:
        client.login()
        if not client.session_id:
            raise RuntimeError("SDK login returned no CGISID")

        # Root page and core layout JS provide routes not visible as ordinary menu links.
        bootstrap_urls = [base + "/", urljoin(base + "/", "js/base/layout_manager.js")]
        for bootstrap_url in bootstrap_urls:
            status, ctype, text = fetch_text(client.transport.session, bootstrap_url)
            name = "root.html" if bootstrap_url.rstrip("/") == base else "layout_manager.js"
            (root / "sources" / name).write_text(text, encoding="utf-8", errors="replace")
            for child in extract_routes(text):
                edges["__root__"].add(child)
                if child not in queued:
                    queued.add(child)
                    discovered.append(child)

        with sync_playwright() as p:
            browser = launch_browser(p, headless=headless)
            ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1100})
            ctx.add_cookies([{"name": "CGISID", "value": client.session_id, "url": base}])
            page = ctx.new_page()
            page.route("**/*", recorder.route)
            page.on("request", recorder.request)
            page.on("response", recorder.response)
            page.on("dialog", lambda d: d.dismiss())

            index = 0
            while discovered and index < max_routes:
                route = discovered.popleft()
                index += 1
                recorder.route_label = route
                source_url = urljoin(base + "/", route)
                status, ctype, source = fetch_text(client.transport.session, source_url)
                source_file = root / "sources" / f"{index:03d}_{safe_slug(route)}.html"
                source_file.write_text(source, encoding="utf-8", errors="replace")

                child_labels = route_labels(source, source_route=route)
                source_children = extract_routes(source, source_route=route)
                for child in source_children:
                    edges[route].add(child)
                    if child in child_labels:
                        labels[(route, child)] = child_labels[child]
                    if child not in queued:
                        queued.add(child)
                        discovered.append(child)

                ok, reason = browser_open_route(page, base, route)
                browser_state: dict[str, object] | None = None
                if ok:
                    browser_state = capture_browser_state(page, root, index, route)
                    for child in browser_state["rendered_routes"]:  # type: ignore[index]
                        if not isinstance(child, str):
                            continue
                        edges[route].add(child)
                        if child not in queued:
                            queued.add(child)
                            discovered.append(child)

                route_meta[route] = {
                    "index": index,
                    "source_url": source_url,
                    "source_status": status,
                    "source_content_type": ctype,
                    "source_file": str(source_file.relative_to(root)).replace("\\", "/"),
                    "source_title": route_title_from_source(source),
                    "source_children": source_children,
                    "browser_ok": ok,
                    "browser_reason": reason,
                    "browser": browser_state,
                }

            try:
                browser.close()
            except Exception:
                pass

    recorder.save()
    paths = shortest_paths(edges, labels)
    edge_rows: list[dict[str, str]] = []
    for parent in sorted(edges):
        for child in sorted(edges[parent]):
            edge_rows.append({
                "parent": parent,
                "child": child,
                "label": labels.get((parent, child), ""),
            })

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "routes": route_meta,
        "edges": edge_rows,
        "shortest_menu_paths": paths,
        "blocked_request_count": len(recorder.blocked),
        "queue_remaining": list(discovered),
    }
    (root / "webui_routes.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    with (root / "webui_route_edges.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["parent", "child", "label"])
        writer.writeheader()
        writer.writerows(edge_rows)

    lines = [
        "# NR2301 WebUI route inventory",
        "",
        "Source-driven read-only inventory from the physical router.",
        "Raw screenshots and HTML may contain local device values and stay private.",
        "",
        "| Route | Menu path | Source | Browser | Screenshot |",
        "|---|---|---:|---|---|",
    ]
    for route, meta in sorted(route_meta.items(), key=lambda kv: int(kv[1]["index"])):
        path = " → ".join(paths.get(route, [route]))
        browser = meta.get("browser") or {}
        shot = browser.get("screenshot", "") if isinstance(browser, dict) else ""
        lines.append(
            f"| `{route}` | {path.replace('|', '/')} | {meta.get('source_status')} | "
            f"{'OK' if meta.get('browser_ok') else meta.get('browser_reason')} | `{shot}` |"
        )
    lines.append("")
    (root / "WEBUI_ROUTE_MAP.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "routes": len(route_meta),
        "browser_ok": sum(1 for v in route_meta.values() if v.get("browser_ok")),
        "source_ok": sum(1 for v in route_meta.values() if v.get("source_status") == 200),
        "edges": len(edge_rows),
        "blocked_requests": len(recorder.blocked),
        "queue_remaining": len(discovered),
        "completed": not discovered,
        "evidence_dir": str(root),
    }
    (root / "webui_route_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    zip_path = shutil.make_archive(str(root), "zip", root_dir=root)
    print("WEBUI_ROUTE_SUMMARY = " + json.dumps(summary, sort_keys=True))
    print(f"WEBUI_ROUTE_ZIP = {zip_path}")
    print("WEBUI_ROUTE_CRAWL = " + ("COMPLETE" if summary["completed"] else "BOUNDED_PARTIAL"))


if __name__ == "__main__":
    main()
