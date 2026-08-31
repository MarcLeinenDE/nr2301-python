# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os
import re

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_INTEGRATION") != "1":
    pytest.skip(
        "SMS recovery test requires NR2301_INTEGRATION=1",
        allow_module_level=True,
    )


def _client() -> NR2301Client:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")
    router = NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=5.0,
    )
    router.login()
    return router


def _test_number() -> str:
    raw = os.environ.get("NR2301_SMS_TEST_NUMBER", "").strip()
    if not raw:
        pytest.skip("NR2301_SMS_TEST_NUMBER is required")
    compact = re.sub(r"[\s()/.\-]", "", raw)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("0"):
        compact = "+49" + compact[1:]
    if not re.fullmatch(r"\+[1-9]\d{6,14}", compact):
        pytest.fail("NR2301_SMS_TEST_NUMBER has an unsupported format")
    return compact


def _normalize_number(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"[\s()/.\-]", "", value.strip().rstrip(","))
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("0"):
        compact = "+49" + compact[1:]
    return compact if re.fullmatch(r"\+[1-9]\d{6,14}", compact) else None


def _sms_object(response: Mapping[str, object]) -> Mapping[str, object]:
    sms = response.get("sms")
    if not isinstance(sms, Mapping):
        pytest.fail("SMS response did not contain an sms object")
    return sms


def _rows_from_page(response: Mapping[str, object]) -> list[Mapping[str, object]]:
    sms = _sms_object(response)
    try:
        resp = int(sms.get("resp", -999))
    except (TypeError, ValueError):
        pytest.fail("SMS list returned a non-integer resp")
    if resp != 0:
        pytest.fail(f"SMS list returned resp={resp}")
    node_list = sms.get("node_list", {})
    if node_list in (None, ""):
        return []
    if not isinstance(node_list, Mapping):
        pytest.fail("SMS list node_list is not an object")
    rows = []
    for item in node_list.values():
        if isinstance(item, Mapping):
            rows.append(item)
    return rows


def _all_messages(router: NR2301Client, list_type: int) -> dict[str, Mapping[str, object]]:
    first = router.sms.list_by_type(list_type, page_index=1)
    sms = _sms_object(first)
    try:
        page_count = int(sms.get("page_count", 0) or 0)
    except (TypeError, ValueError):
        pytest.fail("SMS list returned a non-integer page_count")
    rows = _rows_from_page(first)
    for page in range(2, max(page_count, 1) + 1):
        rows.extend(_rows_from_page(router.sms.list_by_type(list_type, page_index=page)))
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        value = row.get("id")
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            continue
        text = str(value).strip()
        if text.isdigit():
            result[text] = row
    return result


def _decoded_body(value: object) -> tuple[str | None, str]:
    if not isinstance(value, str):
        return None, "MISSING"
    text = value.strip()
    if re.fullmatch(r"(?:[0-9A-Fa-f]{4})+", text):
        try:
            decoded = bytes.fromhex(text).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return None, "HEX_UNDECODABLE"
        return decoded, "UTF16BE_HEX"
    return text, "PLAINTEXT"


def _latest_matching(messages: dict[str, Mapping[str, object]], target: str) -> tuple[str, Mapping[str, object]] | None:
    matches = [
        (int(message_id), message_id, row)
        for message_id, row in messages.items()
        if _normalize_number(row.get("address")) == target
    ]
    if not matches:
        return None
    _, message_id, row = max(matches, key=lambda item: item[0])
    return message_id, row


def test_recover_existing_send_and_reply_without_resend() -> None:
    router = _client()
    target = _test_number()
    try:
        outbox = _all_messages(router, 1)
        inbox = _all_messages(router, 0)
        print(f"SMS_RECOVERY_COUNTS inbox={len(inbox)} outbox={len(outbox)}")

        outbound = _latest_matching(outbox, target)
        if outbound is None:
            pytest.fail("no Outbox message for configured test number was found")
        outbound_id, outbound_row = outbound
        decoded, representation = _decoded_body(outbound_row.get("body"))
        prefix_match = isinstance(decoded, str) and decoded.startswith("NR2301 SDK E2E ")
        print(
            "SMS_RECOVERY_OUTBOX "
            f"representation={representation} synthetic_prefix_match={'YES' if prefix_match else 'NO'}"
        )
        if not prefix_match:
            pytest.fail("latest Outbox message for test number was not the synthetic E2E SMS")

        inbound = _latest_matching(inbox, target)
        if inbound is None:
            pytest.fail("no inbound SMS from configured test number was found")
        reply_id, reply_row = inbound
        before_read = reply_row.get("read")
        print(f"SMS_RECOVERY_INBOX candidate_found=YES read_before={before_read}")

        detail = router.sms.get_by_id(reply_id)
        detail_sms = _sms_object(detail)
        fields = ",".join(sorted(str(key) for key in detail_sms.keys()))
        print(f"SMS_RECOVERY_GET_BY_ID fields={fields or '-'}")

        if str(detail_sms.get("id", "")).strip() != reply_id:
            pytest.fail("get_by_id returned a different SMS ID")
        if _normalize_number(detail_sms.get("address")) != target:
            pytest.fail("get_by_id address did not match configured test number")
        decoded_reply, reply_representation = _decoded_body(detail_sms.get("body"))
        if not decoded_reply:
            pytest.fail("get_by_id returned no decodable inbound body")
        print(
            "SMS_RECOVERY_RESULT "
            f"reply_body_representation={reply_representation} send_reply_get_by_id=OK"
        )
    finally:
        router.close()
