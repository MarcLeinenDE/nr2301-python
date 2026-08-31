# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare current and historical NR2301 pre-auth request transports.

This diagnostic intentionally does NOT read NR2301_PASSWORD and does not call
account/login. It only exercises anonymous/pre-auth reads needed to understand
`account/get_rand` behavior.

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

import requests

BASE_URL = os.environ.get("NR2301_URL", "http://192.168.1.1").rstrip("/")
TIMEOUT = 10.0

HISTORICAL_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "NR2301-Auth-Transport-Probe/1",
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
            if lowered in {"rand", "password", "cgisid"}:
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


def show(label: str, status: int | None, headers: dict[str, str], payload: Any) -> None:
    print(f"\n=== {label} ===")
    print(f"HTTP: {status}")
    print(f"Content-Type: {headers.get('Content-Type') or headers.get('content-type') or '<missing>'}")
    if any(key.lower() == "set-cookie" for key in headers):
        print("Set-Cookie: <present; value redacted>")
    else:
        print("Set-Cookie: <absent>")
    print(json.dumps(sanitize(payload), indent=2, ensure_ascii=False))


def requests_json_post(path: str, method: str, body: dict[str, Any]) -> None:
    session = requests.Session()
    try:
        response = session.post(
            f"{BASE_URL}/api.cgi",
            params={"path": path, "method": method, "timeout": "10"},
            json=body,
            timeout=TIMEOUT,
        )
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text
        show(
            f"requests/json {path}/{method}",
            response.status_code,
            dict(response.headers),
            payload,
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
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text
        show(
            f"requests/historical-shape {path}/{method}",
            response.status_code,
            dict(response.headers),
            payload,
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
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text
        show("anonymous control router/get_feature_list", response.status_code, dict(response.headers), payload)
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

    # Use one identical known-good-shape user_id for all variants so only the
    # transport representation changes between calls.
    user_id = random_user_id()
    rand_body = {"type": "admin", "user_id": user_id}
    print("\nGenerated user_id shape: [a-z0-9]{8} (actual value intentionally not printed)")
    requests_json_post("account", "get_rand", rand_body)
    requests_historical_post("account", "get_rand", rand_body)
    urllib_historical_post("account", "get_rand", rand_body)

    print("\nInterpretation guide:")
    print("- historical variants succeed but requests/json fails: transport representation matters")
    print("- urllib succeeds but both requests variants fail: library/session-level behavior matters")
    print("- all get_rand variants return the same result: investigate router/session/account state next")


if __name__ == "__main__":
    main()
