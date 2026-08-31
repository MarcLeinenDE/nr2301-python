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


def _hex(text: str) -> str:
    return text.encode("utf-16-be", errors="surrogatepass").hex().upper()


def _matches_number(row: Mapping[str, object], expected: str) -> bool:
    return _normalize_observed_number(row.get("address")) == expected


def test_sms_send_receive_reply_and_get_by_id() -> None:
    """Send one synthetic SMS, then verify the operator's real reply end-to-end.

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

        # Confirm the synthetic message reached the router's Outbox without
        # exposing its phone number or body in test output.
        deadline = time.monotonic() + 20.0
        outbound_id: str | None = None
        while time.monotonic() < deadline and outbound_id is None:
            current = _all_messages(router, 1)
            for key, row in current.items():
                if key in outbox_before:
                    continue
                if _matches_number(row, target) and row.get("body") == _hex(outbound_text):
                    outbound_id = key
                    break
            if outbound_id is None:
                time.sleep(1.0)
        if outbound_id is None:
            pytest.fail("sent synthetic SMS was not uniquely confirmed in Outbox")
        print("SMS_E2E_OUTBOX synthetic_send_readback=OK")

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
        if not isinstance(detail_sms.get("body"), str) or not detail_sms.get("body"):
            pytest.fail("get_by_id inbound body was missing")
        print("SMS_E2E_RESULT send_outbox_reply_inbox_get_by_id=OK")
    finally:
        router.close()
