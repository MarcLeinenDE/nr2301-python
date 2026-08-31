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


def _body_class(value: object) -> tuple[str, str]:
    decoded, representation = _decoded_body(value)
    if decoded == _DRAFT_V1:
        return "A", representation
    if decoded == _DRAFT_V2:
        return "B", representation
    if isinstance(decoded, str) and decoded.startswith("NR2301 SDK draft test "):
        return "SYNTHETIC_OTHER", representation
    return "OTHER", representation


def _row_is_synthetic(row: Mapping[str, object]) -> bool:
    body_class, _ = _body_class(row.get("body"))
    return (
        _address_form(row.get("address")) in {"BARE", "TRAILING_COMMA"}
        and body_class in {"A", "B", "SYNTHETIC_OTHER"}
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


def _detail_profile(
    detail_sms: Mapping[str, object],
    *,
    expected_id: str,
    phase: str,
) -> str:
    if str(detail_sms.get("id", "")).strip() != expected_id:
        pytest.fail("get_by_id returned a different draft ID")

    body_class, representation = _body_class(detail_sms.get("body"))
    decoded, _ = _decoded_body(detail_sms.get("body"))
    decoded_length = len(decoded) if isinstance(decoded, str) else -1
    address_form = _address_form(detail_sms.get("address"))
    try:
        detail_type = int(detail_sms.get("type", -1))
    except (TypeError, ValueError):
        pytest.fail("get_by_id type was not numeric")

    print(
        f"SMS_DRAFT_DETAIL phase={phase} body_class={body_class} "
        f"representation={representation} decoded_length={decoded_length} "
        f"address_form={address_form} type={detail_type}"
    )
    if address_form not in {"BARE", "TRAILING_COMMA"}:
        pytest.fail("get_by_id address did not match the synthetic draft")
    if detail_type != 2:
        pytest.fail("get_by_id did not report draft type=2")
    return body_class


def test_sms_draft_create_get_update_delete_roundtrip() -> None:
    router = _client()
    before_ids: set[str] = set()
    created_id: str | None = None
    try:
        before = _all_drafts(router)
        before_ids = set(before)
        print(f"SMS_DRAFT_STATE before_count={len(before)}")

        created = router.sms.save_draft(_SYNTHETIC_RECIPIENT, _DRAFT_V1)
        create_status = _save_status(created)
        print(
            "SMS_DRAFT_ACTION create "
            f"resp={create_status[0]} save_succ={create_status[1]} save_fail={create_status[2]}"
        )
        if create_status != (0, 1, 0):
            pytest.fail("new Draft save did not return the verified success triple")

        after_create = _all_drafts(router)
        create_new_ids = set(after_create) - before_ids
        if len(create_new_ids) != 1:
            pytest.fail("draft create did not produce exactly one new Draft ID")
        created_id = next(iter(create_new_ids))
        print("SMS_DRAFT_STATE created_id_detected=OK")

        created_row = after_create[created_id]
        list_class, list_representation = _body_class(created_row.get("body"))
        address_form = _address_form(created_row.get("address"))
        try:
            draft_type = int(created_row.get("type", -1))
        except (TypeError, ValueError):
            pytest.fail("created draft type was not numeric")
        print(
            "SMS_DRAFT_LIST phase=create "
            f"address_form={address_form} body_class={list_class} "
            f"body_representation={list_representation} type={draft_type}"
        )
        if list_class != "A" or draft_type != 2:
            pytest.fail("created Draft list row did not contain the expected synthetic Draft")

        create_detail = _sms_object(router.sms.get_by_id(created_id))
        safe_fields = ",".join(sorted(str(key) for key in create_detail.keys()))
        print(f"SMS_GET_BY_ID fields={safe_fields or '-'}")
        if _detail_profile(create_detail, expected_id=created_id, phase="create") != "A":
            pytest.fail("created Draft detail did not contain body A")

        updated = router.sms.save_draft(
            _SYNTHETIC_RECIPIENT,
            _DRAFT_V2,
            message_id=created_id,
        )
        update_status = _save_status(updated)
        print(
            "SMS_DRAFT_ACTION existing_id_save "
            f"resp={update_status[0]} save_succ={update_status[1]} save_fail={update_status[2]}"
        )
        if update_status != (0, 1, 0):
            pytest.fail("existing-ID Draft save did not return the verified success triple")

        after_update = _all_drafts(router)
        update_new_ids = set(after_update) - set(after_create)
        original_detail = _sms_object(router.sms.get_by_id(created_id))
        original_class = _detail_profile(
            original_detail,
            expected_id=created_id,
            phase="after_existing_id_save_original",
        )

        new_classes: list[str] = []
        for index, message_id in enumerate(sorted(update_new_ids, key=int), start=1):
            detail = _sms_object(router.sms.get_by_id(message_id))
            new_classes.append(
                _detail_profile(
                    detail,
                    expected_id=message_id,
                    phase=f"after_existing_id_save_new_{index}",
                )
            )

        if original_class == "B" and not update_new_ids:
            behavior = "IN_PLACE"
        elif original_class == "A" and len(update_new_ids) == 1 and new_classes == ["B"]:
            behavior = "COPY_ON_SAVE"
        else:
            behavior = "UNRESOLVED"

        print(
            "SMS_DRAFT_UPDATE_SEMANTICS "
            f"behavior={behavior} original_body_class={original_class} "
            f"new_id_count={len(update_new_ids)} "
            f"new_body_classes={','.join(new_classes) if new_classes else '-'}"
        )
        if behavior == "UNRESOLVED":
            pytest.fail("existing-ID sms.save produced an unresolved Draft state transition")

    finally:
        # Delete only Draft IDs created after this test's initial snapshot and
        # carrying the synthetic Draft marker. Never touch pre-existing Drafts.
        try:
            current = _all_drafts(router)
            cleanup_ids = [
                key
                for key, row in current.items()
                if key not in before_ids and _row_is_synthetic(row)
            ]
            print(f"SMS_DRAFT_CLEANUP candidate_count={len(cleanup_ids)}")
            for key in sorted(cleanup_ids, key=int):
                deleted = router.sms.delete(key)
                status = _delete_status(deleted)
                print(
                    "SMS_DRAFT_CLEANUP delete "
                    f"resp={status[0]} del_succ={status[1]} del_fail={status[2]}"
                )
                if status != (0, 1, 0):
                    pytest.fail("synthetic Draft cleanup delete did not report success")

            final = _all_drafts(router)
            leftovers = [key for key in cleanup_ids if key in final]
            if leftovers:
                pytest.fail("synthetic SMS draft remained after cleanup")
            print("SMS_DRAFT_CLEANUP synthetic_draft_absent=OK")
        finally:
            router.close()
