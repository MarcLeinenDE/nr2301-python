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


def _contacts(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.contacts_by_location(
        LOCAL_LOCATION,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    if not isinstance(values, list):
        raise RuntimeError("getcontactbylocation did not return contactlist as a list")
    return [item for item in values if isinstance(item, Mapping)]


def _indexes(items: list[Mapping[str, Any]]) -> set[int]:
    result: set[int] = set()
    for item in items:
        value = _as_int(item.get("index"))
        if value is not None:
            result.add(value)
    return result


def _find_by_index(items: list[Mapping[str, Any]], index: int) -> Mapping[str, Any] | None:
    for item in items:
        if _as_int(item.get("index")) == index:
            return item
    return None


def _groups(router: NR2301Client) -> list[Mapping[str, Any]]:
    response = router.phonebook.groups()
    values = response.get("grouplist")
    if not isinstance(values, list):
        raise RuntimeError("query_group did not return grouplist as a list")
    return [item for item in values if isinstance(item, Mapping)]


def _find_group(router: NR2301Client, name: str) -> Mapping[str, Any] | None:
    for item in _groups(router):
        if item.get("name") == name and _as_int(item.get("index")) is not None:
            return item
    return None


def _create_group(router: NR2301Client, name: str) -> int:
    response = router.call("phonebook", "addnew_group", data={"name": name})
    group = _find_group(router, name)
    if group is None:
        raise RuntimeError(f"addnew_group failed readback: {_result_text(response)}")
    index = _as_int(group.get("index"))
    if index is None:
        raise RuntimeError("created group has no usable index")
    return index


def _delete_group(router: NR2301Client, index: int) -> None:
    router.call("phonebook", "delete_group", data={"index": str(index)})


def _delete_index(router: NR2301Client, index: int) -> bool:
    response = router.call(
        "phonebook",
        "delete_pb",
        data={
            "delete_pb": {
                "location": "0",
                "count": "1",
                "indexarray": str(index),
            }
        },
    )
    absent = index not in _indexes(_contacts(router))
    print(f"CLEANUP_INDEX_{index}_RESULT = {_result_text(response)}")
    print(f"CLEANUP_INDEX_{index}_ABSENT = {absent}")
    return absent


def _cleanup_new_indexes(router: NR2301Client, initial_indexes: set[int]) -> bool:
    success = True
    for _ in range(3):
        current = _indexes(_contacts(router))
        new_indexes = sorted(current - initial_indexes)
        if not new_indexes:
            return success
        for index in new_indexes:
            try:
                if not _delete_index(router, index):
                    success = False
            except Exception as exc:  # pragma: no cover - physical recovery path
                print(f"CLEANUP_INDEX_{index}_WARNING = {type(exc).__name__}")
                success = False
    return success and _indexes(_contacts(router)) == initial_indexes


def _create_contact(
    router: NR2301Client,
    *,
    name: str,
    mobile: str,
    home: str,
    office: str,
    email: str,
    group: int,
    initial_indexes: set[int],
) -> tuple[int, Mapping[str, Any]]:
    response = router.call(
        "phonebook",
        "addnew_pb",
        data={
            "addnew_pb": {
                "location": "0",
                "name": name,
                "mobile": mobile,
                "home": home,
                "office": office,
                "email": email,
                "group": str(group),
            }
        },
    )
    current = _contacts(router)
    new_indexes = _indexes(current) - initial_indexes
    if len(new_indexes) != 1:
        raise RuntimeError(
            f"addnew_pb did not create exactly one new index; result={_result_text(response)}"
        )
    index = next(iter(new_indexes))
    row = _find_by_index(current, index)
    if row is None:
        raise RuntimeError("new contact index disappeared before baseline readback")
    print(f"CREATE_RESULT                 = {_result_text(response)}")
    print(f"CREATE_INDEX                  = {index}")
    return index, row


def _field_value(row: Mapping[str, Any], field: str) -> Any:
    if field == "group":
        return _as_int(row.get(field))
    return row.get(field)


def _emit_baseline(label: str, row: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    for field in ("name", "mobile", "home", "office", "email", "group"):
        observed = _field_value(row, field)
        exp = expected[field]
        print(f"FIELD_{label}_BASE_{field.upper()}_MATCH = {observed == exp}")
        print(f"FIELD_{label}_BASE_{field.upper()}_EMPTY = {observed in ('', None)}")
        print(f"FIELD_{label}_BASE_{field.upper()}_TYPE  = {type(observed).__name__}")


def _probe_field(
    router: NR2301Client,
    *,
    field: str,
    serial: int,
    group_a: int,
    group_b: int,
    initial_indexes: set[int],
    run_prefix: str,
) -> None:
    baseline: dict[str, Any] = {
        "name": f"{run_prefix}-{serial}-N0",
        "mobile": f"555100{serial:04d}",
        "home": f"555200{serial:04d}",
        "office": f"555300{serial:04d}",
        "email": f"field-{serial}-a@example.invalid",
        "group": group_a,
    }
    requested_target: dict[str, Any] = dict(baseline)
    if field == "name":
        requested_target[field] = f"{run_prefix}-{serial}-N1"
    elif field == "mobile":
        requested_target[field] = f"555110{serial:04d}"
    elif field == "home":
        requested_target[field] = f"555210{serial:04d}"
    elif field == "office":
        requested_target[field] = f"555310{serial:04d}"
    elif field == "email":
        requested_target[field] = f"field-{serial}-b@example.invalid"
    elif field == "group":
        requested_target[field] = group_b
    else:  # pragma: no cover
        raise ValueError(field)

    index, baseline_row = _create_contact(
        router,
        name=str(baseline["name"]),
        mobile=str(baseline["mobile"]),
        home=str(baseline["home"]),
        office=str(baseline["office"]),
        email=str(baseline["email"]),
        group=int(baseline["group"]),
        initial_indexes=initial_indexes,
    )

    label = field.upper()
    _emit_baseline(label, baseline_row, baseline)
    observed_baseline = {
        key: _field_value(baseline_row, key)
        for key in ("name", "mobile", "home", "office", "email", "group")
    }

    payload = {
        "location": "0",
        "index": str(index),
        "name": str(requested_target["name"]),
        "mobile": str(requested_target["mobile"]),
        "home": str(requested_target["home"]),
        "office": str(requested_target["office"]),
        "email": str(requested_target["email"]),
        "group": str(requested_target["group"]),
    }
    response = router.call("phonebook", "update_pb", data={"update_pb": payload})
    row = _find_by_index(_contacts(router), index)
    print(f"FIELD_{label}_UPDATE_RESULT = {_result_text(response)}")
    print(f"FIELD_{label}_SAME_INDEX    = {row is not None}")
    if row is not None:
        observed = _field_value(row, field)
        before = observed_baseline[field]
        desired = requested_target[field]
        print(f"FIELD_{label}_TARGET_MATCH  = {observed == desired}")
        print(f"FIELD_{label}_BASELINE_MATCH = {observed == before}")
        print(f"FIELD_{label}_CHANGED_FROM_BASELINE = {observed != before}")
        print(f"FIELD_{label}_EMPTY         = {observed in ('', None)}")
        others_stable = all(
            _field_value(row, key) == observed_baseline[key]
            for key in observed_baseline
            if key != field
        )
        print(f"FIELD_{label}_OTHERS_STABLE_FROM_OBSERVED_BASE = {others_stable}")

    current_indexes = _indexes(_contacts(router))
    print(f"FIELD_{label}_NEW_INDEX_COUNT = {len(current_indexes - initial_indexes)}")
    if not _cleanup_new_indexes(router, initial_indexes):
        raise RuntimeError(f"cleanup failed after {field} update probe")


def main() -> None:
    _require_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as router:
        router.login()
        initial_contacts = _contacts(router)
        initial_indexes = _indexes(initial_contacts)
        initial_groups = _groups(router)
        print(f"INITIAL_LOCAL_CONTACT_COUNT   = {len(initial_contacts)}")
        print(f"INITIAL_GROUP_COUNT           = {len(initial_groups)}")
        if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") == "1" and initial_contacts:
            raise RuntimeError("expected zero local contacts before field-specific profiler")

        suffix = uuid.uuid4().hex[:6]
        run_prefix = f"SDK-UF-{suffix}"
        group_a_name = f"{run_prefix}-GA"
        group_b_name = f"{run_prefix}-GB"
        group_a: int | None = None
        group_b: int | None = None

        try:
            group_a = _create_group(router, group_a_name)
            group_b = _create_group(router, group_b_name)
            print("GROUP_SETUP_READBACK          = OK")

            for serial, field in enumerate(
                ("name", "mobile", "home", "office", "email", "group"), start=1
            ):
                _probe_field(
                    router,
                    field=field,
                    serial=serial,
                    group_a=group_a,
                    group_b=group_b,
                    initial_indexes=initial_indexes,
                    run_prefix=run_prefix,
                )

            final_indexes = _indexes(_contacts(router))
            print(f"FINAL_INDEX_SET_MATCH         = {final_indexes == initial_indexes}")
            if final_indexes != initial_indexes:
                raise RuntimeError("final local contact index set does not match initial baseline")
            print("PHONEBOOK_UPDATE_FIELD_PROFILER = PASS")
        finally:
            _cleanup_new_indexes(router, initial_indexes)
            if group_b is not None:
                try:
                    _delete_group(router, group_b)
                except Exception as exc:  # pragma: no cover
                    print(f"CLEANUP_GROUP_B_WARNING       = {type(exc).__name__}")
            if group_a is not None:
                try:
                    _delete_group(router, group_a)
                except Exception as exc:  # pragma: no cover
                    print(f"CLEANUP_GROUP_A_WARNING       = {type(exc).__name__}")
            final_group_names = {
                item.get("name")
                for item in _groups(router)
                if isinstance(item.get("name"), str)
            }
            print(f"FINAL_SYNTHETIC_GROUP_PRESENT = {group_a_name in final_group_names or group_b_name in final_group_names}")


if __name__ == "__main__":
    main()
