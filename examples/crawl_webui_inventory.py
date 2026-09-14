# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nr2301 import NR2301Client


ACTION_RE = re.compile(
    r"(?i)\b(apply|save|ok|cancel|add|create|delete|remove|edit|modify|submit|"
    r"connect|disconnect|reboot|restart|reset|restore|upgrade|update|upload|"
    r"send|block|unblock|enable|disable|on|off|logout|log\s*out)\b"
)
DANGER_RE = re.compile(
    r"(?i)\b(usb|management[_ -]?mode|engineering|firmware|factory\s*reset|"
    r"reboot|restart|restore|upgrade)\b"
)
MUTATION_RE = re.compile(
    r"(?is)(?:method=|[\"']method[\"']\s*:\s*[\"'])[^&\"']*"
    r"(?:set|edit|write|delete|remove|add|create|save|apply|update|clear|"
    r"switch|enable|disable|reboot|restart|reset|restore|upgrade|factory|usb)"
)
VOLATILE_RE = re.compile(
    r"(?i)(?:\b\d+(?:[.,]\d+)?(?:\s*(?:kbps|mbps|gbps|bytes|kbytes|mbytes|gbytes|%))?\b|"
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b|"
    r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b|"
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b)"
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


def safe_slug(value: str, *, limit: int = 64) -> str:
    value = re.sub(r"\s+", "_", value.strip().lower())
    value = re.sub(r"[^a-z0-9._-]+", "", value)
    return (value or "state")[:limit]


def normalized_fingerprint(url: str, title: str, body: str) -> str:
    stable = VOLATILE_RE.sub("#", body)
    stable = re.sub(r"\s+", " ", stable).strip()
    raw = f"{url}\n{title}\n{stable}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


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


class NetworkRecorder:
    def __init__(self, root: Path, origin: str) -> None:
        self.root = root
        self.origin = origin
        self.path_label = "bootstrap"
        self.events: list[dict[str, object]] = []
        self.blocked: list[dict[str, object]] = []

    def request(self, req: Any) -> None:
        if not req.url.startswith(self.origin):
            return
        headers = {
            k: v
            for k, v in dict(req.headers).items()
            if k.lower()
            not in {"cookie", "authorization", "x-csrf-token", "x-xsrf-token"}
        }
        self.events.append(
            {
                "kind": "request",
                "path": self.path_label,
                "time": datetime.now(timezone.utc).isoformat(),
                "method": req.method,
                "url": req.url,
                "headers": headers,
                "post_data": req.post_data,
            }
        )

    def response(self, resp: Any) -> None:
        if resp.url.startswith(self.origin):
            self.events.append(
                {
                    "kind": "response",
                    "path": self.path_label,
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
        is_writeish = req.method.upper() not in {"GET", "HEAD", "OPTIONS"} and (
            MUTATION_RE.search(probe) or DANGER_RE.search(probe)
        )
        if is_writeish:
            item = {
                "time": datetime.now(timezone.utc).isoformat(),
                "path": self.path_label,
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
                "reason": "read-only WebUI inventory crawler blocked mutation-like request",
            }
            self.blocked.append(item)
            self.events.append({"kind": "blocked", **item})
            route.abort()
        else:
            route.continue_()

    def save(self) -> None:
        (self.root / "webui_network.json").write_text(
            json.dumps(self.events, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        (self.root / "webui_blocked_requests.json").write_text(
            json.dumps(self.blocked, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )


DOM_INVENTORY_JS = r"""
() => {
  const visible = e => {
    const s = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' &&
           Number(s.opacity || 1) !== 0 && r.width > 0 && r.height > 0;
  };
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();

  function cssPath(el) {
    if (!(el instanceof Element)) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
      let part = cur.tagName.toLowerCase();
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter(x => x.tagName === cur.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      cur = parent;
      if (parts.length >= 8) break;
    }
    return parts.join(' > ');
  }

  function interactiveAncestor(el) {
    let cur = el;
    for (let i = 0; cur && i < 7; i++, cur = cur.parentElement) {
      if (!visible(cur)) continue;
      const s = getComputedStyle(cur);
      const role = (cur.getAttribute('role') || '').toLowerCase();
      const tab = cur.getAttribute('tabindex');
      if (
        ['A','BUTTON','SUMMARY'].includes(cur.tagName) ||
        cur.hasAttribute('onclick') ||
        ['link','button','menuitem','tab','treeitem'].includes(role) ||
        (tab !== null && Number(tab) >= 0) ||
        s.cursor === 'pointer'
      ) return cur;
    }
    return null;
  }

  const all = [...document.querySelectorAll('body *')];
  const seen = new Set();
  const candidates = [];
  for (const textEl of all) {
    if (!visible(textEl)) continue;
    const txt = norm(textEl.innerText || textEl.textContent);
    if (!txt || txt.length > 120) continue;
    const target = interactiveAncestor(textEl);
    if (!target || ['INPUT','SELECT','TEXTAREA','OPTION','LABEL'].includes(target.tagName)) continue;
    const t = norm(target.innerText || target.textContent);
    if (!t || t.length > 180) continue;
    const path = cssPath(target);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    const r = target.getBoundingClientRect();
    candidates.push({
      tag: target.tagName.toLowerCase(),
      id: target.id || '',
      class_name: typeof target.className === 'string' ? target.className : '',
      text: t,
      href: target.getAttribute('href') || '',
      role: target.getAttribute('role') || '',
      tabindex: target.getAttribute('tabindex'),
      onclick: target.getAttribute('onclick') || '',
      cursor: getComputedStyle(target).cursor,
      css_path: path,
      rect: {x:r.x, y:r.y, width:r.width, height:r.height},
    });
  }

  const frames = [...document.querySelectorAll('iframe,frame')].map(x => ({
    src: x.src || x.getAttribute('src') || '',
    name: x.name || '',
    id: x.id || ''
  }));

  return {
    url: location.href,
    title: document.title,
    body_text: norm(document.body ? document.body.innerText : ''),
    html: document.documentElement.outerHTML,
    candidates,
    frames,
  };
}
"""


def candidate_is_navigation(item: dict[str, Any]) -> bool:
    text = str(item.get("text") or "").strip()
    if not text or len(text) > 120:
        return False
    probe = " ".join(
        str(item.get(k) or "")
        for k in ("text", "id", "class_name", "href", "role", "onclick")
    )
    if DANGER_RE.search(probe) or ACTION_RE.search(text):
        return False
    low = probe.lower()
    if any(
        token in low
        for token in (
            "checkbox",
            "radio",
            "switch",
            "toggle",
            "slider",
            "dropdown-toggle",
            "form-control",
            "btn-danger",
            "btn-primary",
            "submit",
        )
    ):
        return False
    return True


def candidate_score(item: dict[str, Any]) -> tuple[int, int, str]:
    text = str(item.get("text") or "")
    score = 0
    if item.get("href"):
        score += 8
    if item.get("onclick"):
        score += 8
    if item.get("role") in {"menuitem", "tab", "treeitem", "link"}:
        score += 8
    if item.get("cursor") == "pointer":
        score += 5
    if item.get("tag") in {"a", "summary"}:
        score += 4
    if re.search(
        r"(?i)\b(network|user|wi-?fi|app|module|internet|security|firewall|nat|"
        r"lan|wan|system|maintenance|sms|sim|vpn|status|settings?|advanced|"
        r"port|filter|dmz|upnp|routing|device|statistics|information)\b",
        text,
    ):
        score += 6
    if len(text) <= 40:
        score += 2
    return (-score, len(text), text.lower())


def spec_from_candidate(item: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(item.get("id") or ""),
        "css_path": str(item.get("css_path") or ""),
        "text": str(item.get("text") or ""),
        "tag": str(item.get("tag") or ""),
    }


CLICK_SPEC_JS = r"""
spec => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  let el = null;
  if (spec.id) el = document.getElementById(spec.id);
  if (!el && spec.css_path) {
    try { el = document.querySelector(spec.css_path); } catch (_) {}
  }
  if (!el && spec.text) {
    const nodes = [...document.querySelectorAll('body *')];
    el = nodes.find(x => norm(x.innerText || x.textContent) === spec.text) || null;
  }
  if (!el) return {ok:false, reason:'not-found'};
  const text = norm(el.innerText || el.textContent);
  if (/(usb|management[_ -]?mode|engineering|firmware|factory\s*reset|reboot|restart|restore|upgrade)/i.test(
        text + ' ' + (el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : '')
      )) return {ok:false, reason:'danger-block'};
  el.scrollIntoView({block:'center', inline:'center'});
  el.click();
  return {ok:true, text, tag:el.tagName, id:el.id || ''};
}
"""


def replay_path(page: Any, base: str, path: list[dict[str, str]]) -> tuple[bool, str]:
    page.goto(base, wait_until="domcontentloaded", timeout=15000)
    settle(page)
    for spec in path:
        try:
            result = page.evaluate(CLICK_SPEC_JS, spec)
        except Exception as exc:
            return False, f"evaluate-error:{type(exc).__name__}"
        if not result or not result.get("ok"):
            return False, str((result or {}).get("reason", "click-failed"))
        settle(page)
    return True, "ok"


def capture_state(
    page: Any,
    root: Path,
    *,
    index: int,
    menu_path: list[dict[str, str]],
) -> dict[str, Any]:
    data = page.evaluate(DOM_INVENTORY_JS)
    label = menu_path[-1]["text"] if menu_path else "home"
    dirname = f"{index:03d}_{safe_slug(label)}"
    state_dir = root / "states" / dirname
    state_dir.mkdir(parents=True, exist_ok=True)

    body_text = str(data.get("body_text") or "")
    html = str(data.pop("html", ""))
    screenshot_rel = f"states/{dirname}/page.png"
    html_rel = f"states/{dirname}/page.html"
    text_rel = f"states/{dirname}/page.txt"
    dom_rel = f"states/{dirname}/dom.json"

    page.screenshot(path=str(root / screenshot_rel), full_page=True)
    (root / html_rel).write_text(html, encoding="utf-8", errors="replace")
    (root / text_rel).write_text(body_text, encoding="utf-8", errors="replace")
    (root / dom_rel).write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    candidates = [
        c for c in data.get("candidates", []) if candidate_is_navigation(c)
    ]
    candidates.sort(key=candidate_score)

    return {
        "index": index,
        "menu_path": [x["text"] for x in menu_path],
        "menu_specs": menu_path,
        "url": data.get("url"),
        "title": data.get("title"),
        "fingerprint": normalized_fingerprint(
            str(data.get("url") or ""), str(data.get("title") or ""), body_text
        ),
        "screenshot": screenshot_rel,
        "html": html_rel,
        "text": text_rel,
        "dom": dom_rel,
        "frames": data.get("frames", []),
        "candidates": candidates,
    }


def archive_static_assets(
    root: Path, client: NR2301Client, recorder: NetworkRecorder
) -> list[dict[str, object]]:
    assets_root = root / "assets"
    assets_root.mkdir(exist_ok=True)
    urls: list[str] = []
    for event in recorder.events:
        if event.get("kind") != "request":
            continue
        url = str(event.get("url") or "")
        if not url or "/api.cgi" in url:
            continue
        parsed = urlsplit(url)
        if Path(parsed.path).suffix.lower() not in {".html", ".js", ".css", ".json"}:
            continue
        if url not in urls:
            urls.append(url)

    manifest: list[dict[str, object]] = []
    for index, url in enumerate(urls, start=1):
        parsed = urlsplit(url)
        rel = parsed.path.lstrip("/") or "index.html"
        rel_path = Path(rel)
        target = assets_root / rel_path
        if target.exists():
            target = target.with_name(
                f"{target.stem}__{index:03d}{target.suffix}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        item: dict[str, object] = {"url": url}
        try:
            response = client.transport.session.get(url, timeout=10.0)
            item["status"] = response.status_code
            item["content_type"] = response.headers.get("content-type", "")
            body = response.content
            item["size"] = len(body)
            if response.ok and len(body) <= 2_500_000:
                target.write_bytes(body)
                item["file"] = str(target.relative_to(root)).replace("\\", "/")
            else:
                item["file"] = None
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            item["file"] = None
        manifest.append(item)

    (root / "webui_assets_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return manifest


def render_tree(states: list[dict[str, Any]]) -> str:
    lines = [
        "# NR2301 WebUI inventory",
        "",
        "Generated from the physical router by the read-only inventory crawler.",
        "Raw screenshots/HTML may contain local device values and should stay private.",
        "",
        "| # | Menu path | URL | Screenshot |",
        "|---:|---|---|---|",
    ]
    for state in states:
        path = " → ".join(state["menu_path"]) if state["menu_path"] else "(home)"
        lines.append(
            f"| {state['index']} | {path.replace('|', '/')} | "
            f"`{state['url']}` | `{state['screenshot']}` |"
        )
    lines.append("")
    return "\n".join(lines)


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
    max_states = int(os.environ.get("NR2301_WEBUI_MAX_STATES", "160"))
    max_depth = int(os.environ.get("NR2301_WEBUI_MAX_DEPTH", "7"))
    max_candidates = int(os.environ.get("NR2301_WEBUI_MAX_CANDIDATES", "40"))
    headless = os.environ.get("NR2301_WEBUI_HEADLESS", "1") != "0"

    root = Path(
        os.environ.get(
            "NR2301_WEBUI_INVENTORY_DIR",
            f"webui_inventory_{datetime.now():%Y%m%d-%H%M%S}",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "states").mkdir(exist_ok=True)

    parsed = urlsplit(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    recorder = NetworkRecorder(root, origin)
    queue: deque[list[dict[str, str]]] = deque([[]])
    queued_paths: set[str] = {"[]"}
    seen_fingerprints: dict[str, int] = {}
    states: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    replay_failures: list[dict[str, Any]] = []

    with NR2301Client(
        base, username=username, password=password, timeout=10.0
    ) as client:
        client.login()
        if not client.session_id:
            raise RuntimeError("SDK login returned no CGISID")

        with sync_playwright() as p:
            browser = launch_browser(p, headless=headless)
            ctx = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1440, "height": 1100},
            )
            ctx.add_cookies(
                [{"name": "CGISID", "value": client.session_id, "url": base}]
            )
            page = ctx.new_page()
            page.route("**/*", recorder.route)
            page.on("request", recorder.request)
            page.on("response", recorder.response)
            page.on("dialog", lambda d: d.dismiss())

            while queue and len(states) < max_states:
                menu_path = queue.popleft()
                recorder.path_label = (
                    " > ".join(x["text"] for x in menu_path) or "(home)"
                )
                ok, reason = replay_path(page, base, menu_path)
                if not ok:
                    replay_failures.append(
                        {
                            "menu_path": [x["text"] for x in menu_path],
                            "reason": reason,
                        }
                    )
                    continue

                provisional = capture_state(
                    page, root, index=len(states) + 1, menu_path=menu_path
                )
                fingerprint = provisional["fingerprint"]
                if fingerprint in seen_fingerprints:
                    aliases.append(
                        {
                            "menu_path": provisional["menu_path"],
                            "duplicate_of": seen_fingerprints[fingerprint],
                            "url": provisional["url"],
                        }
                    )
                    dup_dir = root / provisional["screenshot"].split("/page.png")[0]
                    shutil.rmtree(dup_dir, ignore_errors=True)
                    continue

                seen_fingerprints[fingerprint] = provisional["index"]
                states.append(provisional)

                if len(menu_path) >= max_depth:
                    continue

                for candidate in provisional["candidates"][:max_candidates]:
                    spec = spec_from_candidate(candidate)
                    child = menu_path + [spec]
                    key = json.dumps(child, sort_keys=True, ensure_ascii=False)
                    if key in queued_paths:
                        continue
                    queued_paths.add(key)
                    queue.append(child)

            try:
                browser.close()
            except Exception:
                pass

        assets = archive_static_assets(root, client, recorder)

    recorder.save()

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "max_states": max_states,
        "max_depth": max_depth,
        "states": states,
        "aliases": aliases,
        "replay_failures": replay_failures,
        "blocked_request_count": len(recorder.blocked),
        "static_assets": assets,
    }
    (root / "webui_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (root / "WEBUI_TREE.md").write_text(render_tree(states), encoding="utf-8")

    with (root / "webui_menu_paths.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "depth", "menu_path", "url", "screenshot"])
        for state in states:
            writer.writerow(
                [
                    state["index"],
                    len(state["menu_path"]),
                    " > ".join(state["menu_path"]) or "(home)",
                    state["url"],
                    state["screenshot"],
                ]
            )

    summary = {
        "states": len(states),
        "aliases": len(aliases),
        "replay_failures": len(replay_failures),
        "blocked_requests": len(recorder.blocked),
        "static_assets": len(assets),
        "queue_remaining": len(queue),
        "completed": not queue,
        "evidence_dir": str(root),
    }
    (root / "webui_inventory_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    zip_path = shutil.make_archive(str(root), "zip", root_dir=root)
    print("WEBUI_INVENTORY_SUMMARY = " + json.dumps(summary, sort_keys=True))
    print(f"WEBUI_INVENTORY_ZIP = {zip_path}")
    print(
        "WEBUI_INVENTORY = "
        + ("COMPLETE" if summary["completed"] else "BOUNDED_PARTIAL")
    )


if __name__ == "__main__":
    main()
