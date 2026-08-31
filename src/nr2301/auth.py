# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import secrets
import string

LOGIN_RESULTS = {
    0: "username or password error",
    1: "password error",
    2: "username error",
    3: "success",
    4: "login timeout; retry",
    5: "hacking detected",
    6: "account locked",
}


def generate_user_id() -> str:
    """Generate the verified frontend-compatible login client identifier.

    Historical live-working NR2301 clients used exactly eight lowercase
    alphanumeric characters for the `user_id` passed to `account/get_rand`
    and the subsequent `account/login` request.
    """

    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def challenge_response(rand: str, plaintext_password: str) -> str:
    """Return MD5(rand + plaintext_password) as lowercase hexadecimal."""

    value = f"{rand}{plaintext_password}".encode("utf-8")
    return hashlib.md5(value).hexdigest()  # noqa: S324 - protocol compatibility


def login_result_text(result: int | None) -> str:
    if result is None:
        return "missing login result"
    return LOGIN_RESULTS.get(result, f"unknown login result {result}")
