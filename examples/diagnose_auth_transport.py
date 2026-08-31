# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare NR2301 pre-auth request transports and WebUI bootstrap state.

This diagnostic intentionally does NOT read NR2301_PASSWORD and does not call
account/login. It only exercises anonymous/pre-auth requests needed to
understand `account/get_rand` behavior.

Run with:

    python examples/diagnose_auth_transport.py

Optional:

    NR2301_URL=http://192.168.1.1
"""

from __future__ import annotations

import json
import os
import secrets
import string
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

import requests

BASE_URL = os.environ.get("NR2301_URL", "http://192.168.1.1").rstrip("/")
TIMEOUT = 10.0

HISTORICAL_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "NR2301-Auth-Transport-Probe/2",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def random_user_id() -> str:
    alphabet = string.digits + string.ascii_lowercase
    return "".join(secrets.choice(alphabet) for _ in range(8))


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"rand", "password", "cgisid", "session_id"}:
                if isinstance(item, str):
                    result[key] = f"<redacted:string-length={len(item)}>"
                else:
                    result[key] = "<redacted>"
            else:
                result[key] = sanitize(item)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def decode_payload(raw: bytes) -> Any:
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def show(label: str, status: int | None, headers: dict[str, str], payload: Any) -> None:
    print(f"\n=== {label} ===")
    print(f"HTTP: {status}")
    print(f"Content-Type: {headers.get('Content-Type') or headers.get('content-type') or '<missing>'}")
    if any(key.lower() == "set-cookie" for key in headers):
        print("Set-Cookie: <present; value redacted>")
    else:
        print("Set-Cookie: <absent>")
    print(json.dumps(sanitize(payload), indent=2, ensure_ascii=False))


def cookie_names(session: requests.Session) -> list[str]:
    return sorted({cookie.name for cookie in session.cookies})


def requests_json_post(path: str, method: str, body: dict[str, Any]) -> None:
    session = requests.Session()
    try:
        response = session.post(
            f"{BASE_URL}/api.cgi",
            params={"path": path, "method": method, "timeout": "10"},
            json=body,
            timeout=TIMEOUT,
        )
        show(
            f"requests/json {path}/{method}",
            response.status_code,
            dict(response.headers),
            response_payload(response),
        )
    finally:
        session.close()


def requests_historical_post(path: str, method: str, body: dict[str, Any]) -> None:
    session = requests.Session()
    try:
        raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
        response = session.post(
            f"{BASE_URL}/api.cgi?path={path}&method={method}&timeout=10",
            data=raw_body,
            headers=HISTORICAL_HEADERS,
            timeout=TIMEOUT,
        )
        show(
            f"requests/historical-shape {path}/{method}",
            response.status_code,
            dict(response.headers),
            response_payload(response),
        )
    finally:
        session.close()


def urllib_historical_post(path: str, method: str, body: dict[str, Any]) -> None:
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/api.cgi?path={path}&method={method}&timeout=10",
        data=raw_body,
        headers=HISTORICAL_HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            show(
                f"urllib/historical-shape {path}/{method}",
                response.status,
                dict(response.headers.items()),
                decode_payload(raw),
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        show(
            f"urllib/historical-shape {path}/{method}",
            exc.code,
            dict(exc.headers.items()) if exc.headers else {},
            decode_payload(raw),
        )


def requests_get_feature_list() -> None:
    session = requests.Session()
    try:
        response = session.get(
            f"{BASE_URL}/api.cgi",
            params={"path": "router", "method": "get_feature_list", "timeout": "10"},
            timeout=TIMEOUT,
        )
        show(
            "anonymous control router/get_feature_list",
            response.status_code,
            dict(response.headers),
            response_payload(response),
        )
    finally:
        session.close()


def bootstrap_then_preauth(user_id: str) -> None:
    """Load the WebUI root and reuse exactly that session for pre-auth calls."""

    session = requests.Session()
    try:
        root = session.get(
            f"{BASE_URL}/",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 NR2301-Bootstrap-Probe/1",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        parsed = urlparse(root.url)
        print("\n=== WebUI bootstrap GET / ===")
        print(f"HTTP: {root.status_code}")
        print(f"Redirect count: {len(root.history)}")
        print(f"Final path: {parsed.path or '/'}")
        print(f"HTML/body bytes: {len(root.content)}")
        names = cookie_names(session)
        print(f"Session cookie names: {names if names else '<none>'}")
        print("Cookie values are intentionally not printed.")

        raw_retry = json.dumps({"type": "admin"}, separators=(",", ":")).encode("utf-8")
        retry = session.post(
            f"{BASE_URL}/api.cgi?path=account&method=get_retrytimes_and_time&timeout=10",
            data=raw_retry,
            headers=HISTORICAL_HEADERS,
            timeout=TIMEOUT,
        )
        show(
            "same-session after WebUI bootstrap account/get_retrytimes_and_time",
            retry.status_code,
            dict(retry.headers),
            response_payload(retry),
        )

        raw_rand = json.dumps(
            {"type": "admin", "user_id": user_id},
            separators=(",", ":"),
        ).encode("utf-8")
        rand = session.post(
            f"{BASE_URL}/api.cgi?path=account&method=get_rand&timeout=10",
            data=raw_rand,
            headers=HISTORICAL_HEADERS,
            timeout=TIMEOUT,
        )
        show(
            "same-session after WebUI bootstrap account/get_rand",
            rand.status_code,
            dict(rand.headers),
            response_payload(rand),
        )
        names_after = cookie_names(session)
        print(f"Session cookie names after pre-auth calls: {names_after if names_after else '<none>'}")
    finally:
        session.close()


def main() -> None:
    print("NR2301 pre-auth transport diagnostic")
    print(f"Target: {BASE_URL}")
    print("No password is read or transmitted. account/login is not called.")

    requests_get_feature_list()

    retry_body = {"type": "admin"}
    requests_json_post("account", "get_retrytimes_and_time", retry_body)
    requests_historical_post("account", "get_retrytimes_and_time", retry_body)
    urllib_historical_post("account", "get_retrytimes_and_time", retry_body)

    user_id = random_user_id()
    rand_body = {"type": "admin", "user_id": user_id}
    print("\nGenerated user_id shape: [a-z0-9]{8} (actual value intentionally not printed)")
    requests_json_post("account", "get_rand", rand_body)
    requests_historical_post("account", "get_rand", rand_body)
    urllib_historical_post("account", "get_rand", rand_body)

    bootstrap_then_preauth(user_id)

    print("\nInterpretation guide:")
    print("- bootstrap session succeeds where isolated calls fail: WebUI bootstrap/session state matters")
    print("- bootstrap sets a cookie but account calls still return 4: cookie alone is insufficient")
    print("- bootstrap sets no cookie and calls still return 4: move to sanitized browser network capture")
    print("- all variants return the same result: current router/browser flow has another pre-auth difference")


if __name__ == "__main__":
    main()
