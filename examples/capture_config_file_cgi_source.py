# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from nr2301 import NR2301Client


SCRIPT_RE = re.compile(
    r"""<script[^>]+src\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
FORM_RE = re.compile(
    r"""<form\b(?P<attrs>[^>]*)>(?P<body>.*?)</form>""",
    re.IGNORECASE | re.DOTALL,
)
INPUT_RE = re.compile(
    r"""<(?:input|button|select|textarea)\b[^>]*>""",
    re.IGNORECASE,
)
ATTR_RE = re.compile(
    r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(['"])(.*?)\2""",
    re.DOTALL,
)

NEEDLES = (
    "file.cgi",
    "formdata",
    "multipart",
    "upload",
    "restore",
    "backup",
    "config_bak",
    "configuration",
    "download",
    "filename",
    "content-disposition",
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
            "NR2301_INTEGRATION=1 (or stronger gate) is required"
        )


def attrs(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in ATTR_RE.finditer(text):
        result[match.group(1).lower()] = html.unescape(match.group(3))
    return result


def sanitize_name(url: str, index: int) -> str:
    parsed = urlsplit(url)
    name = Path(parsed.path).name or f"asset-{index}.txt"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return f"{index:02d}-{name}"


def relevant_excerpts(text: str, *, radius: int = 700) -> list[dict[str, object]]:
    lower = text.lower()
    spans: list[tuple[int, int, str]] = []

    for needle in NEEDLES:
        start = 0
        while True:
            pos = lower.find(needle, start)
            if pos < 0:
                break
            spans.append(
                (
                    max(0, pos - radius),
                    min(len(text), pos + len(needle) + radius),
                    needle,
                )
            )
            start = pos + len(needle)

    if not spans:
        return []

    spans.sort()
    merged: list[tuple[int, int, set[str]]] = []
    for start, end, needle in spans:
        if merged and start <= merged[-1][1] + 100:
            old_start, old_end, needles = merged[-1]
            needles.add(needle)
            merged[-1] = (old_start, max(old_end, end), needles)
        else:
            merged.append((start, end, {needle}))

    result = []
    for start, end, needles in merged:
        snippet = text[start:end]
        result.append(
            {
                "needles": sorted(needles),
                "start": start,
                "end": end,
                "snippet": snippet,
            }
        )
    return result


def form_inventory(source: str) -> list[dict[str, object]]:
    forms: list[dict[str, object]] = []
    for form_match in FORM_RE.finditer(source):
        form_attrs = attrs(form_match.group("attrs"))
        controls = []
        for control in INPUT_RE.finditer(form_match.group("body")):
            control_attrs = attrs(control.group(0))
            controls.append(
                {
                    key: control_attrs.get(key)
                    for key in ("type", "name", "id", "value", "accept", "formaction", "method")
                    if control_attrs.get(key) is not None
                }
            )
        forms.append(
            {
                "attrs": {
                    key: form_attrs.get(key)
                    for key in ("id", "name", "action", "method", "enctype")
                    if form_attrs.get(key) is not None
                },
                "controls": controls,
            }
        )
    return forms


def fetch_text(session, url: str) -> tuple[int, str, str]:
    response = session.get(url, timeout=15.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    response.encoding = response.encoding or "utf-8"
    return response.status_code, content_type, response.text


def main() -> None:
    require_read_gate()

    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    base_url = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    output_root = Path(
        os.environ.get(
            "NR2301_CONFIG_SOURCE_OUT",
            f"config_file_cgi_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
    ).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    with NR2301Client(
        base_url,
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        session = client.transport.session

        page_url = f"{base_url}/html/set_config.html"
        status, content_type, source = fetch_text(session, page_url)
        (output_root / "00-set_config.html").write_text(source, encoding="utf-8")

        scripts = []
        for match in SCRIPT_RE.finditer(source):
            url = urljoin(page_url, html.unescape(match.group(1)))
            if url not in scripts:
                scripts.append(url)

        assets = [
            {
                "kind": "html",
                "url": page_url,
                "status": status,
                "content_type": content_type,
                "file": "00-set_config.html",
                "forms": form_inventory(source),
                "excerpts": relevant_excerpts(source),
            }
        ]

        for index, url in enumerate(scripts, start=1):
            try:
                script_status, script_type, script_source = fetch_text(session, url)
            except Exception as exc:
                assets.append(
                    {
                        "kind": "script",
                        "url": url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            filename = sanitize_name(url, index)
            (output_root / filename).write_text(script_source, encoding="utf-8")
            assets.append(
                {
                    "kind": "script",
                    "url": url,
                    "status": script_status,
                    "content_type": script_type,
                    "file": filename,
                    "excerpts": relevant_excerpts(script_source),
                }
            )

    report = {
        "page": "html/set_config.html",
        "output_dir": str(output_root),
        "asset_count": len(assets),
        "assets": assets,
    }
    (output_root / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"CONFIG_SOURCE_CAPTURE_DIR = {output_root}")
    print(f"CONFIG_SOURCE_ASSET_COUNT = {len(assets)}")

    relevant_count = 0
    for asset in assets:
        excerpts = asset.get("excerpts")
        forms = asset.get("forms")
        if forms:
            print(
                "CONFIG_FORMS"
                f" file={asset.get('file')}"
                f" value={json.dumps(forms, ensure_ascii=False)}"
            )
        if not excerpts:
            continue
        relevant_count += len(excerpts)
        for number, excerpt in enumerate(excerpts, start=1):
            snippet = str(excerpt["snippet"]).replace("\r", "")
            print(
                "\n=== CONFIG_SOURCE_EXCERPT"
                f" file={asset.get('file')}"
                f" part={number}"
                f" needles={','.join(excerpt['needles'])} ==="
            )
            print(snippet)

    print(f"CONFIG_SOURCE_RELEVANT_EXCERPTS = {relevant_count}")
    print("CONFIG_SOURCE_CAPTURE = PASS")


if __name__ == "__main__":
    main()
