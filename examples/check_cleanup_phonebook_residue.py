# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from nr2301 import NR2301Client


LOCAL_LOCATION = 0
PAGE_CAPACITY = 100
KNOWN_RESIDUE_INDEXES = {3, 4, 5, 6, 7}
KNOWN_SYNTHETIC_MOBILES = {
    "5550200001", "5550200002", "5550200003", "5550200004",
    "5550300001", "5550300002", "5550300003", "5550300004",
    "5550400001",
}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _synthetic_markers(item: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    name = item.get("name")
    mobile = item.get("mobile")
    email = item.get("email")
    return (
        isinstance(name, str) and name.startswith("SDK-PB-"),
        isinstance(mobile, str) and mobile in KNOWN_SYNTHETIC_MOBILES,
        isinstance(email, str) and email.endswith("@example.invalid"),
    )


def _is_known_residue(item: Mapping[str, Any]) -> bool:
    index = _as_int(item.get("index"))
    if index not in KNOWN_RESIDUE_INDEXES:
        return False
    name_marker, mobile_marker, email_marker = _synthetic_markers(item)
    return name_marker or mobile_marker or email_marker


def _delete(router: NR2301Client, index: int) -> bool:
    router.call(
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
    return all(_as_int(item.get("index")) != index for item in _contacts(router))


def main() -> None:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    cleanup_enabled = os.environ.get("NR2301_PHONEBOOK_RESIDUE_CLEANUP") == "1"

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as router:
        router.login()
        current = _contacts(router)

        indexes = sorted(
            index
            for item in current
            if (index := _as_int(item.get("index"))) is not None
        )
        classified = []
        for item in current:
            index = _as_int(item.get("index"))
            markers = _synthetic_markers(item)
            known = _is_known_residue(item)
            classified.append((index, known, markers))
            print(
                "PHONEBOOK_RESIDUE_ROW"
                f" index={index}"
                f" known_residue={known}"
                f" name_marker={markers[0]}"
                f" mobile_marker={markers[1]}"
                f" email_marker={markers[2]}"
            )

        print(f"PHONEBOOK_RESIDUE_COUNT = {len(current)}")
        print(f"PHONEBOOK_RESIDUE_INDEXES = {indexes}")

        if not current:
            print("PHONEBOOK_RESIDUE_CLEANUP = NOT_NEEDED")
            return

        safe = (
            all(index in KNOWN_RESIDUE_INDEXES for index in indexes)
            and len(indexes) == len(current)
            and all(known for _, known, _ in classified)
        )
        print(f"PHONEBOOK_RESIDUE_SAFE_TO_CLEAN = {safe}")

        if not safe:
            raise RuntimeError(
                "current local phonebook does not consist exclusively of the known "
                "synthetic residue; refusing automatic cleanup"
            )

        if not cleanup_enabled:
            print("PHONEBOOK_RESIDUE_CLEANUP = ARMED_NOT_EXECUTED")
            print("Set NR2301_PHONEBOOK_RESIDUE_CLEANUP=1 to remove the classified residue.")
            return

        for index in indexes:
            absent = _delete(router, index)
            print(f"PHONEBOOK_RESIDUE_DELETE index={index} absent={absent}")
            if not absent:
                raise RuntimeError(f"synthetic residue index {index} could not be removed")

        final = _contacts(router)
        if final:
            raise RuntimeError("local phonebook is not empty after residue cleanup")
        print("PHONEBOOK_RESIDUE_CLEANUP = PASS")


if __name__ == "__main__":
    main()
