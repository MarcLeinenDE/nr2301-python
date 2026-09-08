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
        raise SystemExit(
            "Refusing to run: set NR2301_WRITE_INTEGRATION=1 for the dedicated test router."
        )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_text(response: Mapping[str, Any]) -> str:
    value = response.get("result")
    return f"{type(value).__name__}:{value!r}"


def _groups(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.groups()
    values = response.get("grouplist")
    if not isinstance(values, list):
        raise RuntimeError("query_group did not return grouplist as a list")
    return [item for item in values if isinstance(item, Mapping)]


def _find_group(groups: list[Mapping[str, Any]], name: str) -> Mapping[str, Any] | None:
    for item in groups:
        if item.get("name") == name and _as_int(item.get("index")) is not None:
            return item
    return None


def _contacts_local(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.contacts_by_location(
        LOCAL_LOCATION,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    if not isinstance(values, list):
        raise RuntimeError("getcontactbylocation did not return contactlist as a list")
    return [item for item in values if isinstance(item, Mapping)]


def _contact_indexes(items: list[Mapping[str, Any]]) -> set[int]:
    result: set[int] = set()
    for item in items:
        value = _as_int(item.get("index"))
        if value is not None:
            result.add(value)
    return result


def _find_contact(
    items: list[Mapping[str, Any]],
    *,
    index: int | None = None,
    name: str | None = None,
) -> Mapping[str, Any] | None:
    for item in items:
        item_index = _as_int(item.get("index"))
        if index is not None and item_index != index:
            continue
        if name is not None and item.get("name") != name:
            continue
        return item
    return None


def _contact_in_group(router: NR2301Client, group: int, contact_index: int) -> bool:
    response = router.phonebook.contacts_by_group(
        group,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    if not isinstance(values, list):
        return False
    for item in values:
        if isinstance(item, Mapping) and _as_int(item.get("index")) == contact_index:
            return True
    return False


def _delete_contact(router: NR2301Client, contact_index: int) -> bool:
    response = router.call(
        "phonebook",
        "delete_pb",
        data={
            "delete_pb": {
                "location": "0",
                "count": "1",
                "indexarray": str(contact_index),
            }
        },
    )
    absent = _find_contact(_contacts_local(router), index=contact_index) is None
    print(f"CLEANUP_CONTACT_DELETE_RESULT = {_result_text(response)}")
    print(f"CLEANUP_CONTACT_ABSENT        = {absent}")
    return absent


def _delete_group(router: NR2301Client, group_index: int, expected_name: str) -> bool:
    response = router.call(
        "phonebook",
        "delete_group",
        data={"index": str(group_index)},
    )
    absent = _find_group(_groups(router), expected_name) is None
    print(f"CLEANUP_GROUP_DELETE_RESULT   = {_result_text(response)}")
    print(f"CLEANUP_GROUP_ABSENT          = {absent}")
    return absent


def main() -> None:
    _require_gate()

    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    suffix = uuid.uuid4().hex[:6]
    group_a_name = f"SDK-A-{suffix}"
    group_a_renamed = f"SDK-AR-{suffix}"
    group_b_name = f"SDK-B-{suffix}"
    contact_name = f"SDK-C-{suffix}"
    contact_updated = f"SDK-U-{suffix}"
    synthetic_mobile = f"555010{int(suffix, 16) % 10000:04d}"
    synthetic_email = f"sdk-{suffix}@example.invalid"

    group_a_index: int | None = None
    group_b_index: int | None = None
    contact_index: int | None = None
    contact_deleted = False
    group_a_deleted = False
    group_b_deleted = False

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as router:
        router.login()

        initial_groups = _groups(router)
        initial_local = _contacts_local(router)
        initial_contact_indexes = _contact_indexes(initial_local)
        print(f"INITIAL_GROUP_COUNT           = {len(initial_groups)}")
        print(f"INITIAL_LOCAL_CONTACT_COUNT   = {len(initial_local)}")

        try:
            # 1) Create first synthetic group.
            response = router.call(
                "phonebook",
                "addnew_group",
                data={"name": group_a_name},
            )
            group_a = _find_group(_groups(router), group_a_name)
            if group_a is None:
                raise RuntimeError(
                    f"addnew_group did not create the synthetic group; result={_result_text(response)}"
                )
            group_a_index = _as_int(group_a.get("index"))
            if group_a_index is None:
                raise RuntimeError("created group has no usable integer index")
            print(f"GROUP_CREATE_RESULT           = {_result_text(response)}")
            print("GROUP_CREATE_READBACK         = OK")

            # 2) Rename/update first group.
            response = router.call(
                "phonebook",
                "update_group",
                data={"name": group_a_renamed, "index": str(group_a_index)},
            )
            if _find_group(_groups(router), group_a_renamed) is None:
                raise RuntimeError(
                    f"update_group rename was not visible in readback; result={_result_text(response)}"
                )
            print(f"GROUP_UPDATE_RESULT           = {_result_text(response)}")
            print("GROUP_UPDATE_READBACK         = OK")

            # 3) Create second synthetic group as move target.
            response = router.call(
                "phonebook",
                "addnew_group",
                data={"name": group_b_name},
            )
            group_b = _find_group(_groups(router), group_b_name)
            if group_b is None:
                raise RuntimeError(
                    f"second addnew_group did not create the target group; result={_result_text(response)}"
                )
            group_b_index = _as_int(group_b.get("index"))
            if group_b_index is None:
                raise RuntimeError("second created group has no usable integer index")
            print(f"GROUP2_CREATE_RESULT          = {_result_text(response)}")
            print("GROUP2_CREATE_READBACK        = OK")

            # 4) Create one synthetic LOCAL contact using the source-evidenced nested contract.
            response = router.call(
                "phonebook",
                "addnew_pb",
                data={
                    "addnew_pb": {
                        "location": "0",
                        "name": contact_name,
                        "mobile": synthetic_mobile,
                        "home": "",
                        "office": "",
                        "email": synthetic_email,
                        "group": str(group_a_index),
                    }
                },
            )
            after_create = _contacts_local(router)
            created = _find_contact(after_create, name=contact_name)
            if created is not None:
                contact_index = _as_int(created.get("index"))
            if contact_index is None:
                new_indexes = _contact_indexes(after_create) - initial_contact_indexes
                if len(new_indexes) == 1:
                    contact_index = next(iter(new_indexes))
            if contact_index is None:
                raise RuntimeError(
                    f"addnew_pb succeeded/returned but new contact index could not be isolated; "
                    f"result={_result_text(response)}"
                )
            print(f"CONTACT_CREATE_RESULT         = {_result_text(response)}")
            print("CONTACT_CREATE_READBACK       = OK")

            # 5) Update the synthetic contact and verify only synthetic fields locally.
            response = router.call(
                "phonebook",
                "update_pb",
                data={
                    "update_pb": {
                        "location": "0",
                        "index": str(contact_index),
                        "name": contact_updated,
                        "mobile": synthetic_mobile,
                        "home": "",
                        "office": "",
                        "email": synthetic_email,
                        "group": str(group_a_index),
                    }
                },
            )
            updated = _find_contact(_contacts_local(router), index=contact_index)
            if updated is None or updated.get("name") != contact_updated:
                raise RuntimeError(
                    f"update_pb was not visible in readback; result={_result_text(response)}"
                )
            print(f"CONTACT_UPDATE_RESULT         = {_result_text(response)}")
            print("CONTACT_UPDATE_READBACK       = OK")

            # 6) Resolve the still-incomplete move_contacts_to_group.contacts representation.
            # All attempts target only the synthetic contact. Stop at the first exact readback success.
            move_candidates: list[tuple[str, Any]] = [
                ("string_index", str(contact_index)),
                ("comma_string", f"{contact_index},"),
                ("string_list", [str(contact_index)]),
                ("int_list", [contact_index]),
            ]
            move_success = False
            for label, contacts_value in move_candidates:
                response = router.call(
                    "phonebook",
                    "move_contacts_to_group",
                    data={
                        "newgroup": str(group_b_index),
                        "contacts": contacts_value,
                    },
                )
                moved = _contact_in_group(router, group_b_index, contact_index)
                print(f"MOVE_CANDIDATE_{label.upper()}_RESULT = {_result_text(response)}")
                print(f"MOVE_CANDIDATE_{label.upper()}_READBACK = {moved}")
                if moved:
                    print(f"MOVE_CONFIRMED_REPRESENTATION = {label}")
                    move_success = True
                    break

            if not move_success:
                raise RuntimeError(
                    "move_contacts_to_group did not move the synthetic contact with the bounded candidate matrix"
                )

            # 7) Delete the synthetic contact using the source-evidenced nested delete contract.
            contact_deleted = _delete_contact(router, contact_index)
            if not contact_deleted:
                raise RuntimeError("delete_pb did not remove the synthetic contact")
            print("CONTACT_DELETE_VERIFIED       = OK")

            # 8) Delete both synthetic groups and verify absence.
            group_b_deleted = _delete_group(router, group_b_index, group_b_name)
            if not group_b_deleted:
                raise RuntimeError("delete_group did not remove the second synthetic group")
            group_a_deleted = _delete_group(router, group_a_index, group_a_renamed)
            if not group_a_deleted:
                raise RuntimeError("delete_group did not remove the first synthetic group")
            print("GROUP_DELETE_VERIFIED         = OK")

            # Final cardinality check: no synthetic residue should remain.
            final_groups = _groups(router)
            final_local = _contacts_local(router)
            synthetic_group_present = any(
                item.get("name") in {group_a_name, group_a_renamed, group_b_name}
                for item in final_groups
            )
            synthetic_contact_present = any(
                item.get("name") in {contact_name, contact_updated}
                for item in final_local
            )
            print(f"FINAL_GROUP_COUNT             = {len(final_groups)}")
            print(f"FINAL_LOCAL_CONTACT_COUNT     = {len(final_local)}")
            print(f"FINAL_SYNTHETIC_GROUP_PRESENT = {synthetic_group_present}")
            print(f"FINAL_SYNTHETIC_CONTACT_PRESENT = {synthetic_contact_present}")
            if synthetic_group_present or synthetic_contact_present:
                raise RuntimeError("synthetic phonebook residue remains after nominal cleanup")

            print("PHONEBOOK_WRITE_PROFILER       = PASS")

        finally:
            # Best-effort cleanup for interrupted/failed research runs. Only known synthetic
            # IDs/names created by this process are targeted. Never delete a pre-existing row.
            if contact_index is not None and not contact_deleted:
                try:
                    _delete_contact(router, contact_index)
                except Exception as exc:  # pragma: no cover - physical recovery path
                    print(f"CLEANUP_CONTACT_WARNING       = {type(exc).__name__}")

            if group_b_index is not None and not group_b_deleted:
                try:
                    _delete_group(router, group_b_index, group_b_name)
                except Exception as exc:  # pragma: no cover - physical recovery path
                    print(f"CLEANUP_GROUP2_WARNING        = {type(exc).__name__}")

            if group_a_index is not None and not group_a_deleted:
                try:
                    # It may still have the original name if rename failed.
                    names = {group_a_name, group_a_renamed}
                    response = router.call(
                        "phonebook",
                        "delete_group",
                        data={"index": str(group_a_index)},
                    )
                    remaining = _groups(router)
                    present = any(item.get("name") in names for item in remaining)
                    print(f"CLEANUP_GROUP1_DELETE_RESULT  = {_result_text(response)}")
                    print(f"CLEANUP_GROUP1_PRESENT        = {present}")
                except Exception as exc:  # pragma: no cover - physical recovery path
                    print(f"CLEANUP_GROUP1_WARNING        = {type(exc).__name__}")


if __name__ == "__main__":
    main()
