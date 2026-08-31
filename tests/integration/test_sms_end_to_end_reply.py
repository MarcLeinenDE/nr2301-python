# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os
import re
import secrets
import time

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical SMS E2E test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )
if os.environ.get("NR2301_SMS_EXTERNAL_INTEGRATION") != "1":
    pytest.skip(
        "physical SMS E2E test requires NR2301_SMS_EXTERNAL_INTEGRATION=1",
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
        pytest.skip("NR2301_SMS_TEST_NUMBER is required for the SMS E2E test")

    compact = re.sub(r"[\s()/.\-]", "", raw)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("0"):
        # Test-environment convenience only. The public SDK intentionally does
        # not guess a country code. This integration test is explicitly for a
        # German national-format test number supplied by the operator.
        compact = "+49" + compact[1:]

    if not re.fullmatch(r"\+[1-9]\d{6,14}", compact):
        pytest.fail(
            "NR2301_SMS_TEST_NUMBER must be a German national number beginning "
            "with 0, an international 00... number, or an E.164 +... number"
        )
    return compact


def _normalize_observed_number(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"[\s()/.\-]", "", value.strip().rstrip(","))
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("0"):
        compact = "+49" + compact[1:]
    if re.fullmatch(r"\+[1-9]\d{6,14}", compact):
        return compact
    return None


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

    rows: list[Mapping[str, object]] = []
    for item in node_list.values():
        if not isinstance(item, Mapping):
            pytest.fail("SMS list contains a non-object row")
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
        id_text = str(value).strip()
        if id_text.isdigit():
            result[id_text] = row
    return result


def _decoded_body(value: object) -> tuple[str | None, str]:
    if not isinstance(value, str):
        return None, "MISSING"
    text = value.strip()
    if re.fullmatch(r"(?:[0-9A-Fa-f]{4})+", text):
        try:
            return bytes.fromhex(text).decode("utf-16-be"), "UTF16BE_HEX"
        except (ValueError, UnicodeDecodeError):
            return None, "HEX_UNDECODABLE"
    return text, "PLAINTEXT"


def _matches_number(row: Mapping[str, object], expected: str) -> bool:
    return _normalize_observed_number(row.get("address")) == expected


def test_sms_send_receive_reply_and_get_by_id() -> None:
    """Send one synthetic SMS, then verify a real reply end-to-end.

    No phone number or SMS body is printed. The test intentionally waits for a
    manual reply because that verifies the external modem/network path as well
    as inbox polling and get_by_id on a newly arrived inbound message.
    """

    router = _client()
    target = _test_number()
    token = secrets.token_hex(3).upper()
    outbound_text = (
        f"NR2301 SDK E2E {token}. Bitte antworte direkt auf diese SMS, z.B. mit OK."
    )

    try:
        inbox_before = _all_messages(router, 0)
        outbox_before = _all_messages(router, 1)
        print(
            "SMS_E2E_PREFLIGHT "
            f"inbox_count={len(inbox_before)} "
            f"preexisting_inbox_present={'YES' if inbox_before else 'NO'}"
        )

        sent = router.sms.send(target, outbound_text)
        sent_sms = _sms_object(sent)
        try:
            sent_status = (
                int(sent_sms.get("resp", -999)),
                int(sent_sms.get("smsSendSucc", -999)),
                int(sent_sms.get("smsSendFail", -999)),
            )
        except (TypeError, ValueError):
            pytest.fail("SMS send returned non-integer status fields")
        print(
            "SMS_E2E_SEND "
            f"resp={sent_status[0]} send_succ={sent_status[1]} send_fail={sent_status[2]}"
        )

        # Correlate by new Outbox ID plus normalized target number. A previous
        # physical run proved list_by_type body is UTF-16BE hex but also showed
        # that requiring a byte-for-byte full body match is unnecessarily
        # brittle. Body prefix/representation are diagnostic only.
        deadline = time.monotonic() + 20.0
        outbound_id: str | None = None
        outbound_representation = "UNKNOWN"
        outbound_prefix_match = False
        while time.monotonic() < deadline and outbound_id is None:
            current = _all_messages(router, 1)
            candidates = [
                (key, row)
                for key, row in current.items()
                if key not in outbox_before and _matches_number(row, target)
            ]
            if len(candidates) == 1:
                outbound_id, row = candidates[0]
                decoded, outbound_representation = _decoded_body(row.get("body"))
                outbound_prefix_match = isinstance(decoded, str) and decoded.startswith(
                    f"NR2301 SDK E2E {token}"
                )
                break
            if len(candidates) > 1:
                matching: list[tuple[str, Mapping[str, object], str]] = []
                for key, row in candidates:
                    decoded, representation = _decoded_body(row.get("body"))
                    if isinstance(decoded, str) and decoded.startswith(
                        f"NR2301 SDK E2E {token}"
                    ):
                        matching.append((key, row, representation))
                if len(matching) == 1:
                    outbound_id = matching[0][0]
                    outbound_representation = matching[0][2]
                    outbound_prefix_match = True
                    break
                if len(matching) > 1:
                    pytest.fail("multiple new Outbox rows matched the synthetic SMS token")
            time.sleep(1.0)
        if outbound_id is None:
            pytest.fail("sent synthetic SMS was not uniquely confirmed in Outbox")
        print(
            "SMS_E2E_OUTBOX "
            f"synthetic_send_readback=OK representation={outbound_representation} "
            f"prefix_match={'YES' if outbound_prefix_match else 'NO'}"
        )

        print("SMS_E2E_WAIT reply_window_seconds=180 action=REPLY_TO_RECEIVED_SMS")
        reply_deadline = time.monotonic() + 180.0
        reply_id: str | None = None
        reply_row: Mapping[str, object] | None = None
        while time.monotonic() < reply_deadline and reply_id is None:
            current_inbox = _all_messages(router, 0)
            for key, row in current_inbox.items():
                if key in inbox_before:
                    continue
                if _matches_number(row, target):
                    reply_id = key
                    reply_row = row
                    break
            if reply_id is None:
                time.sleep(2.0)

        if reply_id is None or reply_row is None:
            pytest.fail("no new inbound reply from the configured test number arrived in time")
        print("SMS_E2E_INBOX new_reply_detected=OK")

        detail = router.sms.get_by_id(reply_id)
        detail_sms = _sms_object(detail)
        fields = ",".join(sorted(str(key) for key in detail_sms.keys()))
        print(f"SMS_E2E_GET_BY_ID fields={fields or '-'}")

        if str(detail_sms.get("id", "")).strip() != reply_id:
            pytest.fail("get_by_id returned a different inbound SMS ID")
        if _normalize_observed_number(detail_sms.get("address")) != target:
            pytest.fail("get_by_id inbound address did not match the configured test number")
        decoded_reply, reply_representation = _decoded_body(detail_sms.get("body"))
        if not decoded_reply:
            pytest.fail("get_by_id inbound body was missing or undecodable")
        print(
            "SMS_E2E_RESULT "
            f"reply_body_representation={reply_representation} "
            "send_outbox_reply_inbox_get_by_id=OK"
        )
    finally:
        router.close()
