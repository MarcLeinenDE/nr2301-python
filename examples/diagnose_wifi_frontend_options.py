# SPDX-License-Identifier: GPL-3.0-or-later
"""Discover Wi-Fi option tokens from the NR2301's shipped WebUI assets.

This is a read-only static-asset probe. It does not authenticate and does not
call any configuration setter. It extracts small source contexts around Wi-Fi
configuration field names so option tokens can be normalized before physical
write tests.
"""

from __future__ import annotations

import os
import re
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

BASE_URL = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/") + "/"
TIMEOUT = 10.0
MARKERS = (
    "power_level",
    "bandwidth",
    "net_mode",
    "maxassoc",
    "wifi_timed_off",
    "first_channel",
    "last_channel",
    "channel_list",
)


def _same_origin(url: str) -> bool:
    return urlparse(url).netloc == urlparse(BASE_URL).netloc


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _contexts(text: str, marker: str, radius: int = 260) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    needle = marker.lower()
    start = 0
    while True:
        index = lowered.find(needle, start)
        if index < 0:
            break
        left = max(0, index - radius)
        right = min(len(text), index + len(marker) + radius)
        context = _collapse(text[left:right])
        # Static JS should contain no live router secrets. Still avoid printing
        # suspiciously long runs that might be embedded blobs/source maps.
        context = re.sub(r"[A-Za-z0-9+/=_-]{120,}", "<long-token-redacted>", context)
        if context not in found:
            found.append(context)
        if len(found) >= 8:
            break
        start = index + len(marker)
    return found


def main() -> None:
    session = requests.Session()
    print("NR2301 WebUI Wi-Fi option discovery")
    print(f"Target: {BASE_URL.rstrip('/')}")
    print("Read-only: static HTML/JavaScript assets only; no login or setters.\n")

    root = session.get(BASE_URL, timeout=TIMEOUT)
    root.raise_for_status()
    html = root.text

    scripts: list[str] = []
    for raw in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.I):
        url = urljoin(BASE_URL, unescape(raw))
        if _same_origin(url) and url not in scripts:
            scripts.append(url)

    print(f"Same-origin script assets discovered: {len(scripts)}")

    assets: list[tuple[str, str]] = [("<root-html>", html)]
    for url in scripts:
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"WARN: could not fetch {urlparse(url).path}: {type(exc).__name__}")
            continue
        assets.append((urlparse(url).path, response.text))

    any_match = False
    for marker in MARKERS:
        marker_matches: list[tuple[str, str]] = []
        for path, text in assets:
            for context in _contexts(text, marker):
                marker_matches.append((path, context))
        if not marker_matches:
            continue
        any_match = True
        print(f"\n=== {marker} ===")
        for path, context in marker_matches[:12]:
            print(f"[{path}] {context}")

    # Also summarize obvious literal option tokens occurring in the shipped UI.
    corpus = "\n".join(text for _, text in assets)
    token_patterns = {
        "bandwidth-like": r"HT(?:20|40|80|160)(?:/HT(?:20|40|80|160))*",
        "wifi-net-mode-like": r"11[a-z0-9]+",
    }
    for label, pattern in token_patterns.items():
        tokens = sorted(set(re.findall(pattern, corpus, flags=re.I)))
        if tokens:
            print(f"\n{label} tokens: {', '.join(tokens)}")

    if not any_match:
        print("\nNo field-name contexts found in directly referenced script assets.")
        print("The WebUI may load additional chunks dynamically; report this output unchanged.")


if __name__ == "__main__":
    main()
