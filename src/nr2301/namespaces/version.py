# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class VersionInfo(TypedDict, total=False):
    """Known fields returned by `version/get_ww_version`."""

    result: int
    hw_ver: str
    sw_ver: str


class MagicNumberInfo(TypedDict, total=False):
    """Known fields returned by `version/get_magicnumber`."""

    result: int
    magic: str


class VersionNamespace:
    """Read-only helpers for the live-verified `version` namespace."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def info(self) -> VersionInfo:
        """Return the router hardware/software version information."""

        return cast(VersionInfo, self._client.call("version", "get_ww_version"))

    def magic_number(self) -> MagicNumberInfo:
        """Return the router's version magic-number response."""

        return cast(MagicNumberInfo, self._client.call("version", "get_magicnumber"))
