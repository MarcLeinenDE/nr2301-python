# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import html
import json
import os
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from nr2301 import NR2301Client


SCRIPT_RE = re.compile(
    r"""<script[^>]+src\s*=\s*['"]([^'"]+\.js(?:\?[^'"]*)?)['"]""",
    re.IGNORECASE,
)
QUOTED_JS_RE = re.compile(
    r"""['"]([^'"]+\.js(?:\?[^'"]*)?)['"]""",
    re.IGNORECASE,
)
TARGET_RE = re.compile(
    r"""configFileUpload(?:_IE11)?|/file\.cgi|file\.cgi|FormData|"""
    r"""btn_restore_config|config_backup|Action=Upload|Action=Download|"""
    r"""restore_configuration|config_effective|config_upload""",
    re.IGNORECASE,
)


def require_gate() -> None:
    if not any(
        os.environ.get(name) == "1"
        for name in (
            "NR2301_INTEGRATION",
            "NR2301_WRITE_INTEGRATION",
            "NR2301_DESTRUCTIVE_INTEGRATION",
        )
    ):
        raise RuntimeError("NR2301_INTEGRATION=1 (or stronger gate) is required")


def safe_print(value: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(
        value.encode(encoding, errors="backslashreplace").decode(
            encoding, errors="replace"
        )
    )


def same_origin(url: str, origin: str) -> bool:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}" == origin


def normalize_js(base_url: str, candidate: str, origin: str) -> str | None:
    candidate = html.unescape(candidate.strip())
    if not candidate or candidate.startswith(("data:", "javascript:")):
        return None
    url = urljoin(base_url, candidate)
    if not same_origin(url, origin):
        return None
    if not urlsplit(url).path.lower().endswith(".js"):
        return None
    return url


def discover_js(text: str, *, source_url: str, origin: str) -> list[str]:
    out: list[str] = []
    for regex in (SCRIPT_RE, QUOTED_JS_RE):
        for match in regex.finditer(text):
            url = normalize_js(source_url, match.group(1), origin)
            if url and url not in out:
                out.append(url)
    return out


def contexts(text: str, radius: int = 2200) -> list[dict[str, object]]:
    hits = list(TARGET_RE.finditer(text))
    if not hits:
        return []

    spans: list[tuple[int, int, set[str]]] = []
    for hit in hits:
        start = max(0, hit.start() - radius)
        end = min(len(text), hit.end() + radius)
        label = hit.group(0)
        if spans and start <= spans[-1][1] + 200:
            old_start, old_end, labels = spans[-1]
            labels.add(label)
            spans[-1] = (old_start, max(old_end, end), labels)
        else:
            spans.append((start, end, {label}))

    return [
        {
            "start": start,
            "end": end,
            "targets": sorted(labels, key=str.lower),
            "snippet": text[start:end],
        }
        for start, end, labels in spans
    ]


def safe_name(url: str, index: int) -> str:
    path = urlsplit(url).path.strip("/") or "root"
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", path)
    return f"{index:03d}-{value}"


def fetch_text(session, url: str) -> tuple[int, str, str]:
    response = session.get(url, timeout=15.0)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return (
        response.status_code,
        response.headers.get("content-type", ""),
        response.text,
    )


def main() -> None:
    require_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    base = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    parsed = urlsplit(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    root = Path(
        os.environ.get(
            "NR2301_CONFIG_SHARED_OUT",
            f"config_file_cgi_shared_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)

    seeds = [
        base + "/",
        urljoin(base + "/", "js/base/layout_manager.js"),
        urljoin(base + "/", "html/set_config.html"),
    ]

    report_assets: list[dict[str, object]] = []
    queue: deque[str] = deque(seeds)
    queued = set(seeds)
    fetched: set[str] = set()

    with NR2301Client(
        base,
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        session = client.transport.session

        while queue and len(fetched) < 250:
            url = queue.popleft()
            if url in fetched:
                continue
            fetched.add(url)

            try:
                status, content_type, text = fetch_text(session, url)
            except Exception as exc:
                report_assets.append(
                    {
                        "url": url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            filename = safe_name(url, len(fetched))
            (root / filename).write_text(
                text, encoding="utf-8", errors="replace"
            )
            found_contexts = contexts(text)
            discovered = discover_js(text, source_url=url, origin=origin)

            report_assets.append(
                {
                    "url": url,
                    "status": status,
                    "content_type": content_type,
                    "file": filename,
                    "contexts": found_contexts,
                    "discovered_js": discovered,
                }
            )

            for child in discovered:
                if child not in queued:
                    queued.add(child)
                    queue.append(child)

    report = {
        "origin": origin,
        "asset_count": len(report_assets),
        "assets": report_assets,
    }
    (root / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    matching = [
        asset for asset in report_assets if asset.get("contexts")
    ]

    print(f"CONFIG_SHARED_CAPTURE_DIR = {root}")
    print(f"CONFIG_SHARED_ASSET_COUNT = {len(report_assets)}")
    print(f"CONFIG_SHARED_MATCHING_ASSETS = {len(matching)}")

    for asset in matching:
        print(
            "\n=== CONFIG_SHARED_MATCH"
            f" file={asset.get('file')}"
            f" url={asset.get('url')} ==="
        )
        for number, context in enumerate(asset.get("contexts") or [], start=1):
            print(
                f"--- context {number}"
                f" targets={','.join(context.get('targets') or [])} ---"
            )
            safe_print(str(context.get("snippet") or ""))

    print("CONFIG_SHARED_CAPTURE = PASS")


if __name__ == "__main__":
    main()
