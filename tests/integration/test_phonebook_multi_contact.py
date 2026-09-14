# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "phonebook multi-contact test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )

if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") != "1":
    pytest.skip(
        "phonebook multi-contact test requires NR2301_PHONEBOOK_REQUIRE_EMPTY=1",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration
LOCAL_LOCATION = 0
PAGE_CAPACITY = 100


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _contacts(client: NR2301Client) -> list[Mapping[str, object]]:
    response = client.phonebook.contacts_by_location(
        LOCAL_LOCATION,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    assert isinstance(values, list)
    return [item for item in values if isinstance(item, Mapping)]


def _indexes(client: NR2301Client) -> set[int]:
    return {
        index
        for item in _contacts(client)
        if (index := _as_int(item.get("index"))) is not None
    }


def _group_for(client: NR2301Client, index: int) -> int | None:
    for item in _contacts(client):
        if _as_int(item.get("index")) == index:
            return _as_int(item.get("group"))
    return None


def _groups(client: NR2301Client) -> list[Mapping[str, object]]:
    response = client.phonebook.groups()
    values = response.get("grouplist")
    assert isinstance(values, list)
    return [item for item in values if isinstance(item, Mapping)]


def _group_index(client: NR2301Client, name: str) -> int | None:
    for item in _groups(client):
        if item.get("name") == name:
            return _as_int(item.get("index"))
    return None


def _create_group(client: NR2301Client, name: str) -> int:
    response = client.phonebook.add_group(name)
    assert response.get("result") == 0
    index = _group_index(client, name)
    assert index is not None
    return index


def _create_contact(client: NR2301Client, *, name: str, mobile: str, group: int) -> int:
    before = _indexes(client)
    response = client.phonebook.add_contact(
        name,
        location=LOCAL_LOCATION,
        mobile=mobile,
        home="",
        office="",
        email=f"{name.lower()}@example.invalid",
        group=group,
    )
    assert response.get("result") == 0
    created = _indexes(client) - before
    assert len(created) == 1
    return next(iter(created))


def _cleanup(client: NR2301Client, initial_indexes: set[int], group_indexes: list[int]) -> None:
    extras = sorted(_indexes(client) - initial_indexes)
    for index in extras:
        response = client.phonebook.delete_contact(index, location=LOCAL_LOCATION)
        assert response.get("result") == 0

    for index in reversed(group_indexes):
        if any(_as_int(item.get("index")) == index for item in _groups(client)):
            response = client.phonebook.delete_group(index)
            assert response.get("result") == 0


def test_phonebook_plural_helpers_move_delete_and_restore():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        initial_indexes = _indexes(client)
        initial_group_count = len(_groups(client))
        assert not initial_indexes, "preflight requires an empty local phonebook"

        suffix = uuid.uuid4().hex[:6]
        group_indexes: list[int] = []

        try:
            group_a = _create_group(client, f"SDK-PMA-{suffix}")
            group_indexes.append(group_a)
            group_b = _create_group(client, f"SDK-PMB-{suffix}")
            group_indexes.append(group_b)

            first = _create_contact(
                client,
                name=f"SDK-PM1-{suffix}",
                mobile="5559800001",
                group=group_a,
            )
            second = _create_contact(
                client,
                name=f"SDK-PM2-{suffix}",
                mobile="5559800002",
                group=group_a,
            )
            indexes = [first, second]

            print("PLURAL_CREATED_COUNT       =", len(indexes))

            response = client.phonebook.move_contacts_to_group(indexes, group_b)
            print("PLURAL_MOVE_RESULT         =", response.get("result"))
            assert response.get("result") == 0
            assert all(_group_for(client, index) == group_b for index in indexes)
            print("PLURAL_MOVE_READBACK       = OK")

            response = client.phonebook.delete_contacts(indexes, location=LOCAL_LOCATION)
            print("PLURAL_DELETE_RESULT       =", response.get("result"))
            assert response.get("result") == 0
            assert all(index not in _indexes(client) for index in indexes)
            print("PLURAL_DELETE_READBACK     = OK")
        finally:
            _cleanup(client, initial_indexes, group_indexes)

        final_indexes = _indexes(client)
        final_group_count = len(_groups(client))
        print("FINAL_LOCAL_CONTACT_COUNT  =", len(final_indexes))
        print("FINAL_INDEX_SET_MATCH      =", final_indexes == initial_indexes)
        print("FINAL_GROUP_COUNT_MATCH    =", final_group_count == initial_group_count)

        assert final_indexes == initial_indexes
        assert final_group_count == initial_group_count
