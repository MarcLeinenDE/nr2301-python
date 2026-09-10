# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


LOCAL_LOCATION = 0
PAGE_CAPACITY = 100
POLL_ATTEMPTS = 8
POLL_DELAY_SECONDS = 0.25


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
    if "system_err" in response:
        return f"system_err:{type(response.get('system_err')).__name__}"
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


def _contact_matches(
    item: Mapping[str, Any] | None,
    *,
    name: str,
    mobile: str,
    email: str,
    group: int,
) -> tuple[bool, bool, bool, bool]:
    if item is None:
        return False, False, False, False
    return (
        item.get("name") == name,
        item.get("mobile") == mobile,
        item.get("email") == email,
        _as_int(item.get("group")) == group,
    )


def _create_group(router: NR2301Client, name: str) -> tuple[int, Mapping[str, Any]]:
    response = router.call("phonebook", "addnew_group", data={"name": name})
    group = _find_group(_groups(router), name)
    if group is None:
        raise RuntimeError(
            f"addnew_group did not create the synthetic group; result={_result_text(response)}"
        )
    index = _as_int(group.get("index"))
    if index is None:
        raise RuntimeError("created group has no usable integer index")
    return index, response


def _create_contact(
    router: NR2301Client,
    *,
    name: str,
    mobile: str,
    email: str,
    group: int,
) -> tuple[int, Mapping[str, Any]]:
    before = _contacts_local(router)
    before_indexes = {
        index
        for item in before
        if (index := _as_int(item.get("index"))) is not None
    }
    response = router.call(
        "phonebook",
        "addnew_pb",
        data={
            "addnew_pb": {
                "location": "0",
                "name": name,
                "mobile": mobile,
                "home": "",
                "office": "",
                "email": email,
                "group": str(group),
            }
        },
    )
    after = _contacts_local(router)
    created = _find_contact(after, name=name)
    index = _as_int(created.get("index")) if created is not None else None
    if index is None:
        after_indexes = {
            candidate
            for item in after
            if (candidate := _as_int(item.get("index"))) is not None
        }
        new_indexes = after_indexes - before_indexes
        if len(new_indexes) == 1:
            index = next(iter(new_indexes))
    if index is None:
        raise RuntimeError(
            f"addnew_pb returned but the synthetic contact index could not be isolated; "
            f"result={_result_text(response)}"
        )
    return index, response


def _delete_contact(router: NR2301Client, contact_index: int, *, label: str = "CLEANUP") -> bool:
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
    print(f"{label}_CONTACT_DELETE_RESULT = {_result_text(response)}")
    print(f"{label}_CONTACT_ABSENT        = {absent}")
    return absent


def _delete_synthetic_contacts(router: NR2301Client, prefix: str, *, label: str) -> bool:
    success = True
    for _ in range(3):
        matches = [
            item
            for item in _contacts_local(router)
            if isinstance(item.get("name"), str) and item["name"].startswith(prefix)
        ]
        if not matches:
            return success
        indexes = [
            index
            for item in matches
            if (index := _as_int(item.get("index"))) is not None
        ]
        if len(indexes) != len(matches):
            print(f"{label}_CONTACT_INDEX_WARNING = True")
            success = False
        for index in indexes:
            try:
                if not _delete_contact(router, index, label=label):
                    success = False
            except Exception as exc:  # pragma: no cover - physical recovery path
                print(f"{label}_CONTACT_WARNING       = {type(exc).__name__}")
                success = False
    remaining = any(
        isinstance(item.get("name"), str) and item["name"].startswith(prefix)
        for item in _contacts_local(router)
    )
    print(f"{label}_CONTACT_PREFIX_PRESENT = {remaining}")
    return success and not remaining


def _delete_group(router: NR2301Client, group_index: int, names: set[str], *, label: str) -> bool:
    response = router.call(
        "phonebook",
        "delete_group",
        data={"index": str(group_index)},
    )
    remaining = _groups(router)
    present = any(item.get("name") in names for item in remaining)
    print(f"{label}_GROUP_DELETE_RESULT   = {_result_text(response)}")
    print(f"{label}_GROUP_PRESENT         = {present}")
    return not present


def _contact_in_group(router: NR2301Client, group: int, contact_index: int) -> bool:
    response = router.phonebook.contacts_by_group(
        group,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    if not isinstance(values, list):
        return False
    return any(
        isinstance(item, Mapping) and _as_int(item.get("index")) == contact_index
        for item in values
    )


def _probe_update_candidate(
    router: NR2301Client,
    *,
    run_prefix: str,
    label: str,
    group: int,
    candidate_kind: str,
    serial: int,
) -> str:
    contact_prefix = f"{run_prefix}-UP{serial}"
    original_name = f"{contact_prefix}-A"
    target_name = f"{contact_prefix}-B"
    original_mobile = f"555020{serial:04d}"
    target_mobile = f"555030{serial:04d}"
    original_email = f"up{serial}-a@example.invalid"
    target_email = f"up{serial}-b@example.invalid"

    contact_index, create_response = _create_contact(
        router,
        name=original_name,
        mobile=original_mobile,
        email=original_email,
        group=group,
    )
    print(f"UPDATE_{label}_CREATE_RESULT  = {_result_text(create_response)}")
    print(f"UPDATE_{label}_CONTACT_INDEX  = {contact_index}")

    full_strings = {
        "location": "0",
        "index": str(contact_index),
        "name": target_name,
        "mobile": target_mobile,
        "home": "",
        "office": "",
        "email": target_email,
        "group": str(group),
    }
    if candidate_kind == "strings_full":
        data: Mapping[str, Any] = {"update_pb": full_strings}
    elif candidate_kind == "int_ids_full":
        data = {
            "update_pb": {
                **full_strings,
                "location": 0,
                "index": contact_index,
                "group": group,
            }
        }
    elif candidate_kind == "strings_minimal":
        data = {
            "update_pb": {
                "location": "0",
                "index": str(contact_index),
                "name": target_name,
                "mobile": target_mobile,
                "email": target_email,
                "group": str(group),
            }
        }
    elif candidate_kind == "flat_strings":
        data = full_strings
    else:  # pragma: no cover - internal profiler invariant
        raise ValueError(candidate_kind)

    try:
        response = router.call("phonebook", "update_pb", data=data)
        result_text = _result_text(response)
    except Exception as exc:  # pragma: no cover - physical research path
        print(f"UPDATE_{label}_EXCEPTION      = {type(exc).__name__}")
        _delete_synthetic_contacts(router, contact_prefix, label=f"UPDATE_{label}_CLEANUP")
        return "EXCEPTION"

    same_index: Mapping[str, Any] | None = None
    exact_copies: list[Mapping[str, Any]] = []
    flags = (False, False, False, False)
    current: list[Mapping[str, Any]] = []
    for _ in range(POLL_ATTEMPTS):
        current = _contacts_local(router)
        same_index = _find_contact(current, index=contact_index)
        flags = _contact_matches(
            same_index,
            name=target_name,
            mobile=target_mobile,
            email=target_email,
            group=group,
        )
        exact_copies = [
            item
            for item in current
            if _as_int(item.get("index")) != contact_index
            and all(
                _contact_matches(
                    item,
                    name=target_name,
                    mobile=target_mobile,
                    email=target_email,
                    group=group,
                )
            )
        ]
        if all(flags) or exact_copies:
            break
        time.sleep(POLL_DELAY_SECONDS)

    print(f"UPDATE_{label}_RESULT         = {result_text}")
    print(f"UPDATE_{label}_SAME_INDEX     = {same_index is not None}")
    print(f"UPDATE_{label}_NAME_MATCH     = {flags[0]}")
    print(f"UPDATE_{label}_MOBILE_MATCH   = {flags[1]}")
    print(f"UPDATE_{label}_EMAIL_MATCH    = {flags[2]}")
    print(f"UPDATE_{label}_GROUP_MATCH    = {flags[3]}")
    print(f"UPDATE_{label}_COPY_MATCHES   = {len(exact_copies)}")
    print(f"UPDATE_{label}_LOCAL_COUNT    = {len(current)}")

    if all(flags):
        semantics = "IN_PLACE"
    elif exact_copies:
        semantics = "COPY_ON_UPDATE"
    elif any(flags):
        semantics = "PARTIAL"
    else:
        semantics = "NO_VISIBLE_CHANGE"
    print(f"UPDATE_{label}_SEMANTICS      = {semantics}")

    _delete_synthetic_contacts(router, contact_prefix, label=f"UPDATE_{label}_CLEANUP")
    return semantics


def main() -> None:
    _require_gate()

    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    suffix = uuid.uuid4().hex[:6]
    run_prefix = f"SDK-PB-{suffix}"
    group_a_name = f"{run_prefix}-GA"
    group_a_renamed = f"{run_prefix}-GAR"
    group_b_name = f"{run_prefix}-GB"

    group_a_index: int | None = None
    group_b_index: int | None = None
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
        print(f"INITIAL_GROUP_COUNT           = {len(initial_groups)}")
        print(f"INITIAL_LOCAL_CONTACT_COUNT   = {len(initial_local)}")

        if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") == "1" and initial_local:
            raise RuntimeError(
                "phonebook preflight expected zero local contacts; refusing new writes so prior residue can be inspected"
            )

        try:
            # 1) Group create/update lifecycle.
            group_a_index, response = _create_group(router, group_a_name)
            print(f"GROUP_CREATE_RESULT           = {_result_text(response)}")
            print("GROUP_CREATE_READBACK         = OK")

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

            group_b_index, response = _create_group(router, group_b_name)
            print(f"GROUP2_CREATE_RESULT          = {_result_text(response)}")
            print("GROUP2_CREATE_READBACK        = OK")

            # 2) Isolated update_pb candidate matrix. Each candidate gets its own
            # synthetic contact and is cleaned before the next candidate.
            update_candidates = [
                ("STRINGS_FULL", "strings_full"),
                ("INT_IDS_FULL", "int_ids_full"),
                ("STRINGS_MINIMAL", "strings_minimal"),
                ("FLAT_STRINGS", "flat_strings"),
            ]
            update_confirmed = False
            for serial, (label, kind) in enumerate(update_candidates, start=1):
                semantics = _probe_update_candidate(
                    router,
                    run_prefix=run_prefix,
                    label=label,
                    group=group_a_index,
                    candidate_kind=kind,
                    serial=serial,
                )
                if semantics in {"IN_PLACE", "COPY_ON_UPDATE"}:
                    print(f"UPDATE_CONFIRMED_CANDIDATE    = {label}")
                    print(f"UPDATE_CONFIRMED_SEMANTICS    = {semantics}")
                    update_confirmed = True
                    break

            if not update_confirmed:
                print("UPDATE_CONFIRMED_CANDIDATE    = NONE")
                print("UPDATE_CONFIRMED_SEMANTICS    = UNRESOLVED")

            # 3) Fresh synthetic contact for move_contacts_to_group profiling.
            move_name = f"{run_prefix}-MOVE"
            move_mobile = "5550400001"
            move_email = "move@example.invalid"
            move_index, response = _create_contact(
                router,
                name=move_name,
                mobile=move_mobile,
                email=move_email,
                group=group_a_index,
            )
            print(f"MOVE_CONTACT_CREATE_RESULT    = {_result_text(response)}")
            print(f"MOVE_CONTACT_INDEX            = {move_index}")

            move_candidates: list[tuple[str, Any, Any]] = [
                ("STR_GROUP_STR_INDEX", str(group_b_index), str(move_index)),
                ("STR_GROUP_COMMA", str(group_b_index), f"{move_index},"),
                ("STR_GROUP_STRING_LIST", str(group_b_index), [str(move_index)]),
                ("STR_GROUP_INT_LIST", str(group_b_index), [move_index]),
                ("INT_GROUP_STR_INDEX", group_b_index, str(move_index)),
                ("INT_GROUP_COMMA", group_b_index, f"{move_index},"),
                ("INT_GROUP_STRING_LIST", group_b_index, [str(move_index)]),
                ("INT_GROUP_INT_LIST", group_b_index, [move_index]),
            ]
            move_success = False
            for label, newgroup_value, contacts_value in move_candidates:
                try:
                    response = router.call(
                        "phonebook",
                        "move_contacts_to_group",
                        data={
                            "newgroup": newgroup_value,
                            "contacts": contacts_value,
                        },
                    )
                    result_text = _result_text(response)
                except Exception as exc:  # pragma: no cover - physical research path
                    print(f"MOVE_{label}_EXCEPTION        = {type(exc).__name__}")
                    continue

                moved_by_group_read = _contact_in_group(router, group_b_index, move_index)
                local_row = _find_contact(_contacts_local(router), index=move_index)
                moved_by_local_field = (
                    local_row is not None and _as_int(local_row.get("group")) == group_b_index
                )
                print(f"MOVE_{label}_RESULT           = {result_text}")
                print(f"MOVE_{label}_GROUP_READBACK   = {moved_by_group_read}")
                print(f"MOVE_{label}_LOCAL_GROUP      = {moved_by_local_field}")
                if moved_by_group_read and moved_by_local_field:
                    print(f"MOVE_CONFIRMED_REPRESENTATION = {label}")
                    move_success = True
                    break

            if not move_success:
                print("MOVE_CONFIRMED_REPRESENTATION = NONE")

            # 4) Delete all synthetic contacts created by this run, including any
            # possible update copies, then delete both synthetic groups.
            contacts_clean = _delete_synthetic_contacts(
                router,
                run_prefix,
                label="NOMINAL",
            )
            if not contacts_clean:
                raise RuntimeError("synthetic contacts remain after nominal cleanup")

            group_b_deleted = _delete_group(
                router,
                group_b_index,
                {group_b_name},
                label="NOMINAL_GROUP2",
            )
            group_a_deleted = _delete_group(
                router,
                group_a_index,
                {group_a_name, group_a_renamed},
                label="NOMINAL_GROUP1",
            )
            if not group_a_deleted or not group_b_deleted:
                raise RuntimeError("synthetic group cleanup failed")

            final_groups = _groups(router)
            final_local = _contacts_local(router)
            synthetic_group_present = any(
                isinstance(item.get("name"), str) and item["name"].startswith(run_prefix)
                for item in final_groups
            )
            synthetic_contact_present = any(
                isinstance(item.get("name"), str) and item["name"].startswith(run_prefix)
                for item in final_local
            )
            print(f"FINAL_GROUP_COUNT             = {len(final_groups)}")
            print(f"FINAL_LOCAL_CONTACT_COUNT     = {len(final_local)}")
            print(f"FINAL_SYNTHETIC_GROUP_PRESENT = {synthetic_group_present}")
            print(f"FINAL_SYNTHETIC_CONTACT_PRESENT = {synthetic_contact_present}")
            print(f"FINAL_GROUP_COUNT_MATCH       = {len(final_groups) == len(initial_groups)}")
            print(f"FINAL_LOCAL_COUNT_MATCH       = {len(final_local) == len(initial_local)}")
            if synthetic_group_present or synthetic_contact_present:
                raise RuntimeError("synthetic phonebook residue remains after nominal cleanup")

            print("PHONEBOOK_WRITE_PROFILER       = PASS")

        finally:
            # Best-effort cleanup for interrupted/failed research runs. Prefix matching
            # catches both the original synthetic rows and any copy-on-update variants.
            try:
                _delete_synthetic_contacts(router, run_prefix, label="CLEANUP")
            except Exception as exc:  # pragma: no cover - physical recovery path
                print(f"CLEANUP_CONTACT_WARNING       = {type(exc).__name__}")

            if group_b_index is not None and not group_b_deleted:
                try:
                    _delete_group(
                        router,
                        group_b_index,
                        {group_b_name},
                        label="CLEANUP_GROUP2",
                    )
                except Exception as exc:  # pragma: no cover - physical recovery path
                    print(f"CLEANUP_GROUP2_WARNING        = {type(exc).__name__}")

            if group_a_index is not None and not group_a_deleted:
                try:
                    _delete_group(
                        router,
                        group_a_index,
                        {group_a_name, group_a_renamed},
                        label="CLEANUP_GROUP1",
                    )
                except Exception as exc:  # pragma: no cover - physical recovery path
                    print(f"CLEANUP_GROUP1_WARNING        = {type(exc).__name__}")


if __name__ == "__main__":
    main()
