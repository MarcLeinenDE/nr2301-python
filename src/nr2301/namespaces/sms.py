# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


_GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ"
    " !\"#¤%&'()*+,-./"
    "0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXT = set("^{}\\[~]|€")


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


class SMSSendResult(TypedDict, total=False):
    resp: int
    smsSendSucc: int
    smsSendFail: int
    smsRef: Any


class SMSSendResponse(TypedDict, total=False):
    sms: SMSSendResult


class SMSDeleteResult(TypedDict, total=False):
    resp: int
    smsDelSucc: int
    smsDelFail: int


class SMSDeleteResponse(TypedDict, total=False):
    sms: SMSDeleteResult


class SMSNamespace:
    """SMS helpers backed by the normalized public NR2301 contracts."""

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

    def send(
        self,
        recipient: str,
        message: str,
        *,
        timeout: float = 100.0,
    ) -> SMSSendResponse:
        """Send one normal SMS using the exact verified stock-frontend contract.

        `protocol="0"` is intentionally fixed because that is the normal SMS
        flow that was live verified end-to-end. Recipient and message contents
        are not logged or included in raised error messages.
        """

        if not isinstance(recipient, str):
            raise TypeError("recipient must be a str")
        if not isinstance(message, str):
            raise TypeError("message must be a str")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        recipient = recipient.strip()
        message = message.rstrip("\n")
        if not recipient:
            raise ValueError("recipient must not be empty")
        if not message:
            raise ValueError("message must not be empty")

        # nr2301-api documents the logical numeric values and the stock
        # frontend's default toStringData=true wire behavior. The generic SDK
        # transport deliberately does not stringify arbitrary numbers, so this
        # high-level helper emits the verified wire representation explicitly.
        payload = {
            "sms": {
                "id": "-1",
                "gsm7": "1" if _is_gsm7(message) else "0",
                "address": recipient.rstrip(",") + ",",
                "body": _uni_encode(message),
                "date": _sms_time(),
                "protocol": "0",
            }
        }
        response = self._client.call(
            "sms",
            "sms.send",
            data=payload,
            timeout=timeout,
        )
        sms = self._extract_sms(response, method_id="sms/sms.send")
        if not (
            _int_equals(sms.get("resp"), 0)
            and _int_equals(sms.get("smsSendSucc"), 1)
            and _int_equals(sms.get("smsSendFail"), 0)
        ):
            raise APIError(
                "sms/sms.send did not report verified normal-SMS success",
                method_id="sms/sms.send",
                response=_redact_sms_response(response),
            )
        return cast(SMSSendResponse, response)

    def delete(
        self,
        message_id: int | str,
        *,
        timeout: float | None = None,
    ) -> SMSDeleteResponse:
        """Delete one SMS ID and require the live-verified success triple."""

        if isinstance(message_id, bool) or not isinstance(message_id, (int, str)):
            raise TypeError("message_id must be an int or numeric str")
        id_text = str(message_id).strip()
        if not id_text.isdigit():
            raise ValueError("message_id must be a non-negative integer")

        response = self._client.call(
            "sms",
            "sms.delete",
            data={"sms": {"id": id_text}},
            timeout=timeout,
        )
        sms = self._extract_sms(response, method_id="sms/sms.delete")
        if not (
            _int_equals(sms.get("resp"), 0)
            and _int_equals(sms.get("smsDelSucc"), 1)
            and _int_equals(sms.get("smsDelFail"), 0)
        ):
            raise APIError(
                "sms/sms.delete did not report verified deletion success",
                method_id="sms/sms.delete",
                response=response,
            )
        return cast(SMSDeleteResponse, response)

    @staticmethod
    def _extract_sms(response: Mapping[str, Any], *, method_id: str) -> Mapping[str, Any]:
        sms = response.get("sms")
        if not isinstance(sms, Mapping):
            raise ProtocolError(f"{method_id} did not return an sms object")
        return sms


def _is_gsm7(text: str) -> bool:
    return all(ch in _GSM7_BASIC or ch in _GSM7_EXT for ch in text)


def _uni_encode(text: str) -> str:
    """Match the stock frontend UniEncode: UTF-16BE code units as hex."""

    return text.encode("utf-16-be", errors="surrogatepass").hex().upper()


def _sms_time(now: dt.datetime | None = None) -> str:
    """Match the observed frontend GetSmsTime string."""

    current = now.astimezone() if now is not None else dt.datetime.now().astimezone()
    offset = current.utcoffset() or dt.timedelta()
    hours = offset.total_seconds() / 3600.0
    if abs(hours - round(hours)) < 1e-9:
        off = str(abs(int(round(hours))))
    else:
        off = str(abs(hours)).rstrip("0").rstrip(".")
    timezone = ("%2B" if hours >= 0 else "-") + off
    return (
        f"{current.year % 100},{current.month},{current.day},"
        f"{current.hour},{current.minute},{current.second},{timezone}"
    )


def _int_equals(value: Any, expected: int) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) == expected
    except (TypeError, ValueError):
        return False


def _redact_sms_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only non-content send status fields in error details."""

    sms = response.get("sms")
    if not isinstance(sms, Mapping):
        return {"sms": "invalid response object"}
    return {
        "sms": {
            key: sms.get(key)
            for key in ("resp", "smsSendSucc", "smsSendFail", "smsRef")
            if key in sms
        }
    }
