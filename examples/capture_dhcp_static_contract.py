# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from nr2301 import NR2301Client


TARGETS = (
    "router_set_dhcp_static_ip",
    "router_get_dhcp_static_ip",
    "static",
    "mapping",
    "mac",
    "index",
    "toStringData",
)


def main() -> None:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")

    out_dir = Path(
        os.environ.get(
            "NR2301_DHCP_SOURCE_OUT",
            "dhcp_static_contract_capture",
        )
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"

    with NR2301Client(
        base,
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=15.0,
    ) as client:
        client.login()
        session = client.transport.session

        page_url = urljoin(base + "/", "html/set_dhcp.html")
        response = session.get(page_url, timeout=15.0)
        response.raise_for_status()
        page = response.text

        script_urls = []
        for match in re.finditer(
            r"""<script[^>]+src\s*=\s*['"]([^'"]+)['"]""",
            page,
            re.IGNORECASE,
        ):
            url = urljoin(page_url, match.group(1))
            if urlsplit(url).netloc == urlsplit(origin).netloc:
                script_urls.append(url)

        assets = [(page_url, page)]
        for url in script_urls:
            r = session.get(url, timeout=15.0)
            r.raise_for_status()
            assets.append((url, r.text))

    report = {"assets": []}
    for url, text in assets:
        hits = []
        for target in TARGETS:
            for match in re.finditer(re.escape(target), text, re.IGNORECASE):
                start = max(0, match.start() - 2200)
                end = min(len(text), match.end() + 4200)
                snippet = text[start:end]
                hits.append(
                    {
                        "target": target,
                        "start": start,
                        "end": end,
                        "snippet": snippet,
                    }
                )
        if hits:
            report["assets"].append({"url": url, "hits": hits})

    report_path = out_dir / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"DHCP_STATIC_SOURCE_REPORT = {report_path}")
    print("DHCP_STATIC_SOURCE_CAPTURE = PASS")


if __name__ == "__main__":
    main()
