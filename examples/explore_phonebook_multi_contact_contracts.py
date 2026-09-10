# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


LOCAL_LOCATION = 0
PAGE_CAPACITY = 100


def _require_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise SystemExit("Refusing to run without NR2301_WRITE_INTEGRATION=1")
    if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") != "1":
        raise SystemExit("Refusing to run without NR2301_PHONEBOOK_REQUIRE_EMPTY=1")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_text(response: Mapping[str, Any]) -> str:
    if "system_err" in response:
        return f"system_err:{type(response.get('system_err')).__name__}"
    value = response.get("result")
    return f"{type(value).__name__}:{value!r}"


def _contacts(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.contacts_by_location(
        LOCAL_LOCATION,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    if not isinstance(values, list):
        raise RuntimeError("getcontactbylocation did not return a list")
    return [item for item in values if isinstance(item, Mapping)]


def _indexes(router: NR2301Client) -> set[int]:
    return {
        index
        for item in _contacts(router)
        if (index := _as_int(item.get("index"))) is not None
    }


def _contact_group(router: NR2301Client, index: int) -> int | None:
    for item in _contacts(router):
        if _as_int(item.get("index")) == index:
            return _as_int(item.get("group"))
    return None


def _groups(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.groups()
    values = response.get("grouplist")
    if not isinstance(values, list):
        raise RuntimeError("query_group did not return a list")
    return [item for item in values if isinstance(item, Mapping)]


def _group_index(router: NR2301Client, name: str) -> int | None:
    for item in _groups(router):
        if item.get("name") == name:
            return _as_int(item.get("index"))
    return None


def _create_group(router: NR2301Client, name: str) -> int:
    before = {i for item in _groups(router) if (i := _as_int(item.get("index"))) is not None}
    response = router.phonebook.add_group(name)
    if response.get("result") != 0:
        raise RuntimeError(f"add_group failed: {_result_text(response)}")
    index = _group_index(router, name)
    if index is None or index in before:
        raise RuntimeError("created group index could not be isolated")
    return index


def _create_contact(router: NR2301Client, *, serial: int, group: int) -> int:
    before = _indexes(router)
    response = router.phonebook.add_contact(
        f"SDK-MULTI-{serial}",
        location=LOCAL_LOCATION,
        mobile=f"55570{serial:05d}",
        home="",
        office="",
        email=f"multi-{serial}@example.invalid",
        group=group,
    )
    if response.get("result") != 0:
        raise RuntimeError(f"add_contact failed: {_result_text(response)}")
    new = _indexes(router) - before
    if len(new) != 1:
        raise RuntimeError(f"created contact index delta was {len(new)}, expected 1")
    return next(iter(new))


def _cleanup_contacts(router: NR2301Client, initial_indexes: set[int]) -> None:
    for _ in range(3):
        extra = sorted(_indexes(router) - initial_indexes)
        if not extra:
            break
        for index in extra:
            response = router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
            print(f"CLEANUP_INDEX_{index}_RESULT = {_result_text(response)}")
    if _indexes(router) != initial_indexes:
        raise RuntimeError("contact cleanup did not restore the exact initial index set")


def _cleanup_group(router: NR2301Client, index: int | None, names: set[str]) -> None:
    if index is None:
        return
    if not any(item.get("name") in names for item in _groups(router)):
        return
    response = router.phonebook.delete_group(index)
    print(f"CLEANUP_GROUP_{index}_RESULT = {_result_text(response)}")
    if any(item.get("name") in names for item in _groups(router)):
        raise RuntimeError(f"group {index} cleanup failed")


def _move_candidates(indexes: list[int]) -> list[tuple[str, Any]]:
    a, b = indexes
    return [
        ("COMMA_STRING", f"{a},{b}"),
        ("STRING_LIST", [str(a), str(b)]),
        ("INT_LIST", [a, b]),
        ("JSON_ARRAY_STRING", f'["{a}","{b}"]'),
    ]


def _delete_candidates(indexes: list[int]) -> list[tuple[str, Any]]:
    a, b = indexes
    return [
        ("COMMA_STRING", f"{a},{b}"),
        ("STRING_LIST", [str(a), str(b)]),
        ("INT_LIST", [a, b]),
        ("JSON_ARRAY_STRING", f'["{a}","{b}"]'),
    ]


def main() -> None:
    _require_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    suffix = uuid.uuid4().hex[:6]
    group_a_name = f"SDK-MULTI-A-{suffix}"
    group_b_name = f"SDK-MULTI-B-{suffix}"
    group_a: int | None = None
    group_b: int | None = None

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as router:
        router.login()
        initial_indexes = _indexes(router)
        initial_group_count = len(_groups(router))
        print(f"INITIAL_LOCAL_CONTACT_COUNT = {len(initial_indexes)}")
        print(f"INITIAL_GROUP_COUNT         = {initial_group_count}")
        if initial_indexes:
            raise RuntimeError("preflight requires an empty local phonebook")

        move_confirmed: str | None = None
        delete_confirmed: str | None = None
        try:
            group_a = _create_group(router, group_a_name)
            group_b = _create_group(router, group_b_name)
            print("GROUP_SETUP_READBACK        = OK")

            move_indexes = [
                _create_contact(router, serial=101, group=group_a),
                _create_contact(router, serial=102, group=group_a),
            ]
            print(f"MOVE_CONTACT_COUNT          = {len(move_indexes)}")

            for label, contacts_value in _move_candidates(move_indexes):
                response = router.call(
                    "phonebook",
                    "move_contacts_to_group",
                    data={"newgroup": str(group_b), "contacts": contacts_value},
                )
                groups_after = [_contact_group(router, index) for index in move_indexes]
                target_count = sum(value == group_b for value in groups_after)
                print(f"MOVE_{label}_RESULT         = {_result_text(response)}")
                print(f"MOVE_{label}_TARGET_COUNT   = {target_count}")
                print(f"MOVE_{label}_BOTH_MOVED     = {target_count == 2}")
                if target_count == 2:
                    move_confirmed = label
                    break
                for index in move_indexes:
                    if _contact_group(router, index) != group_a:
                        restore = router.phonebook.move_contact_to_group(index, group_a)
                        if restore.get("result") != 0 or _contact_group(router, index) != group_a:
                            raise RuntimeError("failed to restore contact after move candidate")

            print(f"MOVE_MULTI_CONFIRMED        = {move_confirmed or 'NONE'}")

            for index in move_indexes:
                if index in _indexes(router):
                    router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
            if any(index in _indexes(router) for index in move_indexes):
                raise RuntimeError("failed to remove move-profiler contacts")

            for serial, (label, _) in enumerate(_delete_candidates([1, 2]), start=1):
                delete_indexes = [
                    _create_contact(router, serial=200 + serial * 10, group=group_a),
                    _create_contact(router, serial=201 + serial * 10, group=group_a),
                ]
                contacts_value = dict(_delete_candidates(delete_indexes))[label]
                response = router.call(
                    "phonebook",
                    "delete_pb",
                    data={
                        "delete_pb": {
                            "location": "0",
                            "count": "2",
                            "indexarray": contacts_value,
                        }
                    },
                )
                remaining = [index for index in delete_indexes if index in _indexes(router)]
                print(f"DELETE_{label}_RESULT       = {_result_text(response)}")
                print(f"DELETE_{label}_REMAINING    = {len(remaining)}")
                print(f"DELETE_{label}_BOTH_DELETED = {not remaining}")
                if not remaining:
                    delete_confirmed = label
                    break
                for index in remaining:
                    cleanup = router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
                    if cleanup.get("result") != 0 or index in _indexes(router):
                        raise RuntimeError("failed to clean up after delete candidate")

            print(f"DELETE_MULTI_CONFIRMED      = {delete_confirmed or 'NONE'}")
        finally:
            _cleanup_contacts(router, initial_indexes)
            _cleanup_group(router, group_b, {group_b_name})
            _cleanup_group(router, group_a, {group_a_name})

        final_indexes = _indexes(router)
        final_group_count = len(_groups(router))
        print(f"FINAL_LOCAL_CONTACT_COUNT   = {len(final_indexes)}")
        print(f"FINAL_INDEX_SET_MATCH       = {final_indexes == initial_indexes}")
        print(f"FINAL_GROUP_COUNT_MATCH     = {final_group_count == initial_group_count}")

        if move_confirmed is None or delete_confirmed is None:
            raise RuntimeError("multi-contact contract remained unresolved; cleanup completed")
        if final_indexes != initial_indexes or final_group_count != initial_group_count:
            raise RuntimeError("final restore check failed")
        print("PHONEBOOK_MULTI_CONTRACT_PROFILER = PASS")


if __name__ == "__main__":
    main()
