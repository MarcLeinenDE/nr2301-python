# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class OTAUpdatedStatus(TypedDict, total=False):
    fota_auto_upgrade_status: str
    result: str


class OTAQueryState(TypedDict, total=False):
    response: str


class OTANamespace:
    """Read-only OTA status helpers backed by live-verified public contracts.

    This namespace deliberately excludes actions that can start, clear, cancel,
    download or install firmware updates.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def updated_status(self, *, timeout: float | None = None) -> OTAUpdatedStatus:
        """Return the raw firmware-updated notification/status response."""

        return cast(
            OTAUpdatedStatus,
            self._client.call("ota", "get_updated_status", timeout=timeout),
        )

    def query_state(self, *, timeout: float | None = None) -> OTAQueryState:
        """Return the current OTA state without initiating an update check.

        The documented request is `new_query` with exactly ``{"type": 1}``.
        A returned ``response="idle"`` is preserved as a neutral raw state and
        must not be interpreted by the SDK as proof that firmware is current.
        """

        return cast(
            OTAQueryState,
            self._client.call("ota", "new_query", data={"type": 1}, timeout=timeout),
        )
