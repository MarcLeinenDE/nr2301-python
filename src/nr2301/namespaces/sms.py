# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


class SMSBriefInfo(TypedDict, total=False):
    delivery_list: list[Any]
    flash_msg_ids: list[Any]
    memory_full: int
    new_num: int
    unread_num: int


class SMSMessageNode(TypedDict, total=False):
    address: str
    body: str
    contact_id: int
    date: str
    id: int
    location: int
    read: int
    status: int
    type: int


class SMSMailbox(TypedDict, total=False):
    count: int
    node_list: dict[str, SMSMessageNode]
    page_count: int
    resp: int
    total: int


class SMSMailboxResponse(TypedDict, total=False):
    sms: SMSMailbox


class SMSQueryData(TypedDict, total=False):
    ids: str
    resp: int


class SMSQueryResponse(TypedDict, total=False):
    sms: SMSQueryData


class SMSNamespace:
    """SMS helpers whose public request contracts are fully normalized."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def brief_info(self, *, timeout: float | None = None) -> SMSBriefInfo:
        """Return unread/new counts and SMS memory/delivery metadata."""

        return cast(
            SMSBriefInfo,
            self._client.call("sms", "sms.get_brief_info", timeout=timeout),
        )

    def list_by_type(
        self,
        list_type: int,
        *,
        page_index: int = 1,
        timeout: float | None = None,
    ) -> SMSMailboxResponse:
        """List one SMS mailbox using the endpoint's raw `list_type` value.

        The SDK deliberately does not reuse enums from unrelated SMS fields.
        Callers should use the list-type semantics documented by nr2301-api.
        """

        if not isinstance(list_type, int) or isinstance(list_type, bool):
            raise TypeError("list_type must be an int")
        if not isinstance(page_index, int) or isinstance(page_index, bool):
            raise TypeError("page_index must be an int")
        if page_index < 1:
            raise ValueError("page_index must be at least 1")

        return cast(
            SMSMailboxResponse,
            self._client.call(
                "sms",
                "sms.list_by_type",
                data={
                    "sms": {
                        "page_index": page_index,
                        "list_type": list_type,
                    }
                },
                timeout=timeout,
            ),
        )

    def query_ids(
        self,
        *,
        message_type: int,
        read: int,
        location: int,
        timeout: float | None = None,
    ) -> list[str]:
        """Query SMS IDs and return the endpoint's comma-separated IDs as strings.

        `sms.query` has a documented endpoint-specific success rule: `resp == 0`.
        The raw integer filters are intentionally not mapped to invented SDK
        enums because their meanings are endpoint-scoped.
        """

        for name, value in (
            ("message_type", message_type),
            ("read", read),
            ("location", location),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an int")

        response = self._client.call(
            "sms",
            "sms.query",
            data={
                "sms": {
                    "type": message_type,
                    "read": read,
                    "location": location,
                }
            },
            timeout=timeout,
        )
        sms = self._extract_sms(response, method_id="sms/sms.query")
        resp = sms.get("resp")
        if resp != 0:
            raise APIError(
                f"sms/sms.query reported resp={resp!r}",
                method_id="sms/sms.query",
                response=response,
            )

        ids = sms.get("ids")
        if not isinstance(ids, str):
            raise ProtocolError("sms/sms.query did not return string ids on success")

        return [item.strip() for item in ids.split(",") if item.strip()]

    @staticmethod
    def _extract_sms(response: Mapping[str, Any], *, method_id: str) -> Mapping[str, Any]:
        sms = response.get("sms")
        if not isinstance(sms, Mapping):
            raise ProtocolError(f"{method_id} did not return an sms object")
        return sms
