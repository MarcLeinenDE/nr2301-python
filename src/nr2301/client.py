# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import requests

from .auth import challenge_response, generate_user_id, login_result_text
from .exceptions import AuthenticationError, ProtocolError
from .namespaces import (
    DeviceNamespace,
    LANNamespace,
    MobileNamespace,
    SIMNamespace,
    SMSNamespace,
    StatisticsNamespace,
    VersionNamespace,
    WiFiNamespace,
)
from .transport import HTTPTransport


class NR2301Client:
    """Synchronous client for the Zyxel NR2301 local management API."""

    def __init__(
        self,
        base_url: str = "http://zyxel.home",
        *,
        username: str = "admin",
        password: str | None = None,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.transport = HTTPTransport(base_url, session=session, timeout=timeout)
        self._authenticated = False

        # Evidence-backed high-level namespaces. The generic call()/multicall()
        # transport remains available for every documented API method.
        self.version = VersionNamespace(self)
        self.device = DeviceNamespace(self)
        self.mobile = MobileNamespace(self)
        self.sim = SIMNamespace(self)
        self.lan = LANNamespace(self)
        self.wifi = WiFiNamespace(self)
        self.sms = SMSNamespace(self)
        self.statistics = StatisticsNamespace(self)

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def session_id(self) -> str | None:
        return self.transport.session.cookies.get("CGISID")

    def login(self) -> dict[str, Any]:
        if self.password is None:
            raise AuthenticationError("no administrator password was supplied")

        self.transport.session.cookies.pop("CGISID", None)
        self._authenticated = False

        # Match the previously live-working frontend/application flow and
        # protect against consuming the final password attempt during tests.
        retry_state = self.call(
            "account",
            "get_retrytimes_and_time",
            data={"type": "admin"},
            authenticated=False,
        )
        retry_result = _optional_int(retry_state.get("result"))
        if retry_result != 0:
            raise AuthenticationError(
                _preauth_failure_message(
                    self.transport.base_url,
                    "account/get_retrytimes_and_time",
                    retry_state.get("result"),
                ),
                result=retry_result,
            )

        remain_time = _optional_int(retry_state.get("remain_time"))
        retry_times = _optional_int(retry_state.get("retry_times"))
        if remain_time is not None and remain_time > 0:
            raise AuthenticationError(
                f"administrator login is temporarily locked; retry in {remain_time} s"
            )
        if retry_times is not None and retry_times <= 1:
            raise AuthenticationError(
                f"administrator login aborted to protect against lockout; "
                f"only {retry_times} attempt(s) remain"
            )

        user_id = generate_user_id()
        challenge = self.call(
            "account",
            "get_rand",
            data={"type": "admin", "user_id": user_id},
            authenticated=False,
        )

        challenge_result = _optional_int(challenge.get("result"))
        if challenge_result != 0:
            raise AuthenticationError(
                _preauth_failure_message(
                    self.transport.base_url,
                    "account/get_rand",
                    challenge.get("result"),
                ),
                result=challenge_result,
            )
        rand = challenge.get("rand")
        if not isinstance(rand, str) or not rand:
            raise ProtocolError("account/get_rand did not return a usable rand value")

        digest = challenge_response(rand, self.password)
        result = self.call(
            "account",
            "login",
            data={
                "type": "admin",
                "username": self.username,
                "password": digest,
                "user_id": user_id,
            },
            authenticated=False,
        )

        result_code = result.get("result")
        if result_code != 3:
            numeric_result = _optional_int(result_code)
            raise AuthenticationError(
                f"administrator login failed: {login_result_text(numeric_result)}",
                result=numeric_result,
            )

        if not self.session_id:
            raise ProtocolError("login returned success but no CGISID session cookie was established")

        self._authenticated = True
        return result

    def logout(self) -> dict[str, Any] | None:
        if not self._authenticated and not self.session_id:
            return None
        try:
            result = self.call("account", "logout")
            return result
        finally:
            self._authenticated = False
            self.transport.session.cookies.pop("CGISID", None)

    def call(
        self,
        path: str,
        method: str,
        *,
        data: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        if authenticated and not (self._authenticated or self.session_id):
            raise AuthenticationError(
                f"{path}/{method} requires an authenticated session; call login() first"
            )
        return self.transport.call(path, method, data=data, timeout=timeout)

    def multicall(
        self,
        requests_: Sequence[Mapping[str, Any]],
        *,
        timeout: float | None = None,
        authenticated: bool = True,
    ) -> Any:
        if authenticated and not (self._authenticated or self.session_id):
            raise AuthenticationError("multicall requires an authenticated session; call login() first")
        return self.transport.multicall(requests_, timeout=timeout)

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "NR2301Client":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if self._authenticated or self.session_id:
                self.logout()
        finally:
            self.close()


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _preauth_failure_message(base_url: str, method_id: str, result: Any) -> str:
    message = f"{method_id} failed with result={result!r}"
    if _uses_tested_direct_management_ip(base_url) and _optional_int(result) == 4:
        message += (
            "; tested firmware V1.00(ACIY.3)C0 returns result=4 for administrator "
            "pre-auth calls addressed as 192.168.1.1, while the same router/IP "
            "succeeds via the canonical management host http://zyxel.home"
        )
    return message


def _uses_tested_direct_management_ip(base_url: str) -> bool:
    return urlsplit(base_url).hostname == "192.168.1.1"
