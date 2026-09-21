# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


_PASSWORD_RE = re.compile(
    r"^[a-zA-Z0-9`~!@#$%^&*()_+\-={}\|\\;' :\"<>/?.,\[\]]+$"
)
_TIMEOUT_VALUES = {60, 300, 600, 900}


class AccountInfo(TypedDict, total=False):
    modified: int
    password: str
    remaining_time: str
    result: int
    status: str
    total_time: int
    username: str


class AccountNamespace:
    """Administrator-account helpers.

    Account information and password operations are secret-bearing. Callers
    must not log raw responses or password arguments.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def info(self, *, timeout: float | None = None) -> AccountInfo:
        """Return raw administrator account information.

        The firmware response may contain credential-related fields.
        """

        return cast(
            AccountInfo,
            self._client.call(
                "account",
                "get_info",
                data={
                    "type": "admin",
                    "session_id": self._session_id(),
                },
                timeout=timeout,
            ),
        )

    def set_password(
        self,
        new_password: str,
        *,
        timeout: float | None = None,
        verify_login: bool = True,
    ) -> dict[str, Any]:
        """Change the administrator password through the stock-WebUI contract.

        The old password is not sent in the setter body. On success the client
        adopts `new_password`. By default a fresh challenge/login is performed
        immediately to prove that the new credential works.
        """

        self._validate_password(new_password)

        response = self._client.call(
            "account",
            "set_info",
            data={
                "type": "admin",
                "session_id": self._session_id(),
                "password": new_password,
            },
            timeout=timeout,
        )
        result = self._result_code(response)
        if result != 0:
            message = "administrator password change failed"
            if result == -1001:
                message += "; firmware rejected the requested password"
            raise APIError(
                message,
                method_id="account/set_info",
                response={"result": result},
            )

        self._client.password = new_password

        if verify_login:
            # login() deliberately clears the existing CGISID first, so success
            # proves the new credential rather than merely reusing the old
            # authenticated session.
            self._client.login()

        return response

    def set_timeout(
        self,
        seconds: int,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Set the stock-WebUI administrator session timeout."""

        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise TypeError("seconds must be an int")
        if seconds not in _TIMEOUT_VALUES:
            raise ValueError(
                "seconds must be one of 60, 300, 600, or 900"
            )

        response = self._client.call(
            "account",
            "set_info",
            data={
                "type": "admin",
                "session_id": self._session_id(),
                "total_time": str(seconds),
            },
            timeout=timeout,
        )
        result = self._result_code(response)
        if result != 0:
            raise APIError(
                "administrator timeout change failed",
                method_id="account/set_info",
                response={"result": result},
            )
        return response

    def _session_id(self) -> str:
        value = self._client.session_id
        if not isinstance(value, str) or not value:
            raise ProtocolError("authenticated session has no usable CGISID")
        return value

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str):
            raise TypeError("new_password must be a str")
        if len(password) < 5:
            raise ValueError("new_password must contain at least 5 characters")
        if len(password) > 32:
            raise ValueError("new_password must contain at most 32 characters")
        if not _PASSWORD_RE.fullmatch(password):
            raise ValueError(
                "new_password contains characters rejected by the stock frontend"
            )
        if password.isspace():
            raise ValueError("new_password must not consist only of spaces")

    @staticmethod
    def _result_code(response: dict[str, Any]) -> int:
        value = response.get("result")
        if isinstance(value, bool):
            raise ProtocolError("account/set_info returned invalid boolean result")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ProtocolError(
                "account/set_info returned invalid result"
            ) from exc
