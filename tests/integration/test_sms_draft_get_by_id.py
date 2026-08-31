# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os
import re

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical SMS draft test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )

_SYNTHETIC_RECIPIENT = "0000000000"
_DRAFT_V1 = "NR2301 SDK draft test A"
_DRAFT_V2 = "NR2301 SDK draft test B"


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
        pytest.fail("draft list returned a non-integer resp")
    if resp != 0:
        pytest.fail(f"draft list returned resp={resp}")

    node_list = sms.get("node_list", {})
    if node_list in (None, ""):
        return []
    if not isinstance(node_list, Mapping):
        pytest.fail("draft list node_list is not an object")

    rows: list[Mapping[str, object]] = []
    for item in node_list.values():
        if not isinstance(item, Mapping):
            pytest.fail("draft list contains a non-object row")
        rows.append(item)
    return rows


def _all_drafts(router: NR2301Client) -> dict[str, Mapping[str, object]]:
    first = router.sms.list_by_type(2, page_index=1)
    sms = _sms_object(first)
    try:
        page_count = int(sms.get("page_count", 0) or 0)
    except (TypeError, ValueError):
        pytest.fail("draft list returned a non-integer page_count")

    rows = _rows_from_page(first)
    for page in range(2, max(page_count, 1) + 1):
        rows.extend(_rows_from_page(router.sms.list_by_type(2, page_index=page)))

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


def _address_form(value: object) -> str:
    if value == _SYNTHETIC_RECIPIENT:
        return "BARE"
    if value == _SYNTHETIC_RECIPIENT + ",":
        return "TRAILING_COMMA"
    return "OTHER"


def _row_is_synthetic(row: Mapping[str, object]) -> bool:
    decoded, _ = _decoded_body(row.get("body"))
    return (
        _address_form(row.get("address")) in {"BARE", "TRAILING_COMMA"}
        and isinstance(decoded, str)
        and decoded.startswith("NR2301 SDK draft test ")
    )


def _save_status(response: Mapping[str, object]) -> tuple[int, int, int]:
    sms = _sms_object(response)
    try:
        return (
            int(sms.get("resp", -999)),
            int(sms.get("smsSaveSucc", -999)),
            int(sms.get("smsSaveFail", -999)),
        )
    except (TypeError, ValueError):
        pytest.fail("draft save returned non-integer status fields")


def _delete_status(response: Mapping[str, object]) -> tuple[int, int, int]:
    sms = _sms_object(response)
    try:
        return (
            int(sms.get("resp", -999)),
            int(sms.get("smsDelSucc", -999)),
            int(sms.get("smsDelFail", -999)),
        )
    except (TypeError, ValueError):
        pytest.fail("draft delete returned non-integer status fields")


def _assert_detail(
    detail_sms: Mapping[str, object],
    *,
    draft_id: str,
    expected_body: str,
) -> None:
    if str(detail_sms.get("id", "")).strip() != draft_id:
        pytest.fail("get_by_id returned a different draft ID")
    if detail_sms.get("body") != _hex(expected_body):
        pytest.fail("get_by_id body did not match the synthetic draft")

    # The exact save wire request uses a trailing comma. Accept either list/detail
    # presentation until physical evidence establishes whether the router strips it.
    if _address_form(detail_sms.get("address")) not in {"BARE", "TRAILING_COMMA"}:
        pytest.fail("get_by_id address did not match the synthetic draft")
    try:
        detail_type = int(detail_sms.get("type", -1))
    except (TypeError, ValueError):
        pytest.fail("get_by_id type was not numeric")
    if detail_type != 2:
        pytest.fail("get_by_id did not report draft type=2")


def test_sms_draft_create_get_update_delete_roundtrip() -> None:
    router = _client()
    draft_id: str | None = None
    before_ids: set[str] = set()
    try:
        before = _all_drafts(router)
        before_ids = set(before)
        print(f"SMS_DRAFT_STATE before_count={len(before)}")

        created = router.sms.save_draft(_SYNTHETIC_RECIPIENT, _DRAFT_V1)
        resp, succ, fail = _save_status(created)
        print(
            f"SMS_DRAFT_ACTION create resp={resp} save_succ={succ} save_fail={fail}"
        )

        after_create = _all_drafts(router)
        new_ids = set(after_create) - before_ids
        if len(new_ids) != 1:
            pytest.fail("draft create did not produce exactly one new Draft ID")
        draft_id = next(iter(new_ids))
        print("SMS_DRAFT_STATE created_id_detected=OK")

        created_row = after_create[draft_id]
        decoded, representation = _decoded_body(created_row.get("body"))
        prefix_match = isinstance(decoded, str) and decoded.startswith(
            "NR2301 SDK draft test "
        )
        address_form = _address_form(created_row.get("address"))
        try:
            draft_type = int(created_row.get("type", -1))
        except (TypeError, ValueError):
            pytest.fail("created draft type was not numeric")
        print(
            "SMS_DRAFT_LIST "
            f"address_form={address_form} body_representation={representation} "
            f"synthetic_prefix_match={'YES' if prefix_match else 'NO'} type={draft_type}"
        )
        if draft_type != 2:
            pytest.fail("created draft did not read back type=2")

        detail = router.sms.get_by_id(draft_id)
        detail_sms = _sms_object(detail)
        safe_fields = ",".join(sorted(str(key) for key in detail_sms.keys()))
        print(f"SMS_GET_BY_ID fields={safe_fields or '-'}")
        _assert_detail(detail_sms, draft_id=draft_id, expected_body=_DRAFT_V1)
        print(
            "SMS_GET_BY_ID synthetic_draft_readback=OK "
            f"address_form={_address_form(detail_sms.get('address'))}"
        )

        updated = router.sms.save_draft(
            _SYNTHETIC_RECIPIENT,
            _DRAFT_V2,
            message_id=draft_id,
        )
        resp, succ, fail = _save_status(updated)
        print(
            f"SMS_DRAFT_ACTION update resp={resp} save_succ={succ} save_fail={fail}"
        )

        updated_detail = _sms_object(router.sms.get_by_id(draft_id))
        _assert_detail(updated_detail, draft_id=draft_id, expected_body=_DRAFT_V2)
        print("SMS_DRAFT_STATE update_readback=OK")

    finally:
        # Clean up only this run's newly-created ID or rows carrying the synthetic
        # draft prefix. Never delete a pre-existing unrelated draft.
        cleanup_ids: set[str] = set()
        if draft_id is not None:
            cleanup_ids.add(draft_id)
        try:
            current = _all_drafts(router)
            for key, row in current.items():
                if key not in before_ids and _row_is_synthetic(row):
                    cleanup_ids.add(key)

            for key in sorted(cleanup_ids):
                if key not in current:
                    continue
                deleted = router.sms.delete(key)
                resp, succ, fail = _delete_status(deleted)
                print(
                    f"SMS_DRAFT_CLEANUP delete resp={resp} del_succ={succ} del_fail={fail}"
                )

            final = _all_drafts(router)
            leftovers = [key for key in cleanup_ids if key in final]
            if leftovers:
                pytest.fail("synthetic SMS draft remained after cleanup")
            print("SMS_DRAFT_CLEANUP synthetic_draft_absent=OK")
        finally:
            router.close()
