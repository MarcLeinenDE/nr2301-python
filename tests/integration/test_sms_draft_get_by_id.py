# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os

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


def _matches_synthetic(row: Mapping[str, object], body_text: str) -> bool:
    return (
        row.get("address") == _SYNTHETIC_RECIPIENT + ","
        and row.get("body") == _hex(body_text)
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


def test_sms_draft_create_get_update_delete_roundtrip() -> None:
    router = _client()
    draft_id: str | None = None
    try:
        before = _all_drafts(router)
        print(f"SMS_DRAFT_STATE before_count={len(before)}")

        created = router.sms.save_draft(_SYNTHETIC_RECIPIENT, _DRAFT_V1)
        resp, succ, fail = _save_status(created)
        print(
            f"SMS_DRAFT_ACTION create resp={resp} save_succ={succ} save_fail={fail}"
        )

        after_create = _all_drafts(router)
        new_ids = set(after_create) - set(before)
        if len(new_ids) == 1:
            draft_id = next(iter(new_ids))
        else:
            matching = [
                key
                for key, row in after_create.items()
                if key not in before and _matches_synthetic(row, _DRAFT_V1)
            ]
            if len(matching) != 1:
                pytest.fail(
                    "could not uniquely identify the newly created synthetic draft"
                )
            draft_id = matching[0]
        print("SMS_DRAFT_STATE created_id_detected=OK")

        created_row = after_create[draft_id]
        if not _matches_synthetic(created_row, _DRAFT_V1):
            pytest.fail("created draft list read-back did not match synthetic content")
        try:
            draft_type = int(created_row.get("type", -1))
        except (TypeError, ValueError):
            pytest.fail("created draft type was not numeric")
        if draft_type != 2:
            pytest.fail("created draft did not read back type=2")
        print("SMS_DRAFT_STATE create_readback=OK type=2")

        detail = router.sms.get_by_id(draft_id)
        detail_sms = _sms_object(detail)
        safe_fields = ",".join(sorted(str(key) for key in detail_sms.keys()))
        print(f"SMS_GET_BY_ID fields={safe_fields or '-'}")
        if str(detail_sms.get("id", "")).strip() != draft_id:
            pytest.fail("get_by_id returned a different draft ID")
        if detail_sms.get("body") != _hex(_DRAFT_V1):
            pytest.fail("get_by_id body did not match the synthetic draft")
        if detail_sms.get("address") != _SYNTHETIC_RECIPIENT + ",":
            pytest.fail("get_by_id address did not match the synthetic draft")
        try:
            detail_type = int(detail_sms.get("type", -1))
        except (TypeError, ValueError):
            pytest.fail("get_by_id type was not numeric")
        if detail_type != 2:
            pytest.fail("get_by_id did not report draft type=2")
        print("SMS_GET_BY_ID synthetic_draft_readback=OK")

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
        if updated_detail.get("body") != _hex(_DRAFT_V2):
            pytest.fail("updated draft body did not read back")
        if updated_detail.get("address") != _SYNTHETIC_RECIPIENT + ",":
            pytest.fail("updated draft address did not read back")
        print("SMS_DRAFT_STATE update_readback=OK")

    finally:
        # Clean up only IDs that can be tied to this synthetic draft. Never
        # delete an unrelated pre-existing draft merely because the main test failed.
        cleanup_ids: set[str] = set()
        if draft_id is not None:
            cleanup_ids.add(draft_id)
        try:
            current = _all_drafts(router)
            for key, row in current.items():
                if _matches_synthetic(row, _DRAFT_V1) or _matches_synthetic(row, _DRAFT_V2):
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
            leftovers = [
                key
                for key, row in final.items()
                if key in cleanup_ids
                or _matches_synthetic(row, _DRAFT_V1)
                or _matches_synthetic(row, _DRAFT_V2)
            ]
            if leftovers:
                pytest.fail("synthetic SMS draft remained after cleanup")
            print("SMS_DRAFT_CLEANUP synthetic_draft_absent=OK")
        finally:
            router.close()
