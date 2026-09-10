# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "phonebook write tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


pytestmark = pytest.mark.integration
LOCAL_LOCATION = 0
PAGE_CAPACITY = 100


@pytest.fixture(scope="module")
def router():
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as client:
        client.login()
        yield client


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _contacts(router: NR2301Client) -> list[Mapping[str, object]]:
    response = router.phonebook.contacts_by_location(
        LOCAL_LOCATION,
        page_capacity=PAGE_CAPACITY,
        page_index=0,
    )
    values = response.get("contactlist")
    assert isinstance(values, list)
    return [item for item in values if isinstance(item, Mapping)]


def _indexes(router: NR2301Client) -> set[int]:
    return {
        index
        for item in _contacts(router)
        if (index := _as_int(item.get("index"))) is not None
    }


def _find_contact(router: NR2301Client, index: int) -> Mapping[str, object] | None:
    for item in _contacts(router):
        if _as_int(item.get("index")) == index:
            return item
    return None


def _groups(router: NR2301Client) -> list[Mapping[str, object]]:
    response = router.phonebook.groups()
    values = response.get("grouplist")
    assert isinstance(values, list)
    return [item for item in values if isinstance(item, Mapping)]


def _find_group(router: NR2301Client, name: str) -> Mapping[str, object] | None:
    for item in _groups(router):
        if item.get("name") == name and _as_int(item.get("index")) is not None:
            return item
    return None


def _cleanup_new_local_indexes(router: NR2301Client, initial_indexes: set[int]) -> None:
    # Index-delta cleanup is deliberately independent of contact names because
    # raw contact text uses the WebUI codec and other fields can be normalized.
    for _ in range(3):
        new_indexes = sorted(_indexes(router) - initial_indexes)
        if not new_indexes:
            break
        for index in new_indexes:
            response = router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
            assert response.get("result") == 0
            assert index not in _indexes(router)

    assert _indexes(router) == initial_indexes


def _delete_group_if_present(router: NR2301Client, index: int | None, names: set[str]) -> None:
    if index is None:
        return
    if not any(item.get("name") in names for item in _groups(router)):
        return
    response = router.phonebook.delete_group(index)
    assert response.get("result") == 0
    assert not any(item.get("name") in names for item in _groups(router))


def test_phonebook_high_level_write_lifecycle_and_restore(router: NR2301Client):
    initial_indexes = _indexes(router)
    suffix = uuid.uuid4().hex[:6]
    group_a_name = f"SDK-WA-{suffix}"
    group_a_renamed = f"SDK-WAR-{suffix}"
    group_b_name = f"SDK-WB-{suffix}"
    contact_name = f"SDK-WC-{suffix}"
    contact_email = f"sdk-{suffix}@example.invalid"
    mobile_initial = f"555500{int(suffix, 16) % 10000:04d}"
    mobile_updated = f"555600{int(suffix, 16) % 10000:04d}"

    group_a_index = None
    group_b_index = None

    try:
        response = router.phonebook.add_group(group_a_name)
        assert response.get("result") == 0
        group_a = _find_group(router, group_a_name)
        assert group_a is not None
        group_a_index = _as_int(group_a.get("index"))
        assert group_a_index is not None

        response = router.phonebook.update_group(group_a_index, group_a_renamed)
        assert response.get("result") == 0
        assert _find_group(router, group_a_renamed) is not None

        response = router.phonebook.add_group(group_b_name)
        assert response.get("result") == 0
        group_b = _find_group(router, group_b_name)
        assert group_b is not None
        group_b_index = _as_int(group_b.get("index"))
        assert group_b_index is not None

        before_create = _indexes(router)
        response = router.phonebook.add_contact(
            contact_name,
            location=LOCAL_LOCATION,
            mobile=mobile_initial,
            home="",
            office="",
            email=contact_email,
            group=group_a_index,
        )
        assert response.get("result") == 0
        created_indexes = _indexes(router) - before_create
        assert len(created_indexes) == 1
        contact_index = next(iter(created_indexes))

        created = _find_contact(router, contact_index)
        assert created is not None
        assert created.get("mobile") == mobile_initial
        assert _as_int(created.get("group")) == group_a_index

        # This lifecycle keeps its assertions on mobile + group because those
        # are enough to exercise update + membership behavior here. The
        # dedicated text-codec integration test separately proves that name is
        # mutable when WebUI UniEncode serialization is used, including Unicode.
        response = router.phonebook.update_contact(
            contact_index,
            location=LOCAL_LOCATION,
            name=contact_name,
            mobile=mobile_updated,
            home="",
            office="",
            email=contact_email,
            group=group_b_index,
        )
        assert response.get("result") == 0
        updated = _find_contact(router, contact_index)
        assert updated is not None
        assert updated.get("mobile") == mobile_updated
        assert _as_int(updated.get("group")) == group_b_index

        response = router.phonebook.move_contact_to_group(contact_index, group_a_index)
        assert response.get("result") == 0
        moved = _find_contact(router, contact_index)
        assert moved is not None
        assert _as_int(moved.get("group")) == group_a_index

        response = router.phonebook.delete_contact(contact_index, location=LOCAL_LOCATION)
        assert response.get("result") == 0
        assert contact_index not in _indexes(router)

        response = router.phonebook.delete_group(group_b_index)
        assert response.get("result") == 0
        assert _find_group(router, group_b_name) is None
        group_b_index = None

        response = router.phonebook.delete_group(group_a_index)
        assert response.get("result") == 0
        assert _find_group(router, group_a_renamed) is None
        group_a_index = None
    finally:
        _cleanup_new_local_indexes(router, initial_indexes)
        _delete_group_if_present(router, group_b_index, {group_b_name})
        _delete_group_if_present(router, group_a_index, {group_a_name, group_a_renamed})

    assert _indexes(router) == initial_indexes


def test_copy_all_from_sim_to_local_and_restore_local_index_set(router: NR2301Client):
    initial_indexes = _indexes(router)

    try:
        response = router.phonebook.copy_all_from_sim_to_local()
        assert isinstance(response, dict)
        for key in ("sim_count", "count", "duplicate", "failed", "invalid"):
            value = response.get(key)
            assert isinstance(value, int) and not isinstance(value, bool)

        # Do not print or inspect contact content. Any newly copied local rows
        # are test-owned by index delta and are removed below; SIM storage is
        # never modified by this test.
        created_count = len(_indexes(router) - initial_indexes)
        reported_count = response.get("count")
        assert isinstance(reported_count, int) and not isinstance(reported_count, bool)
        assert created_count <= reported_count
    finally:
        _cleanup_new_local_indexes(router, initial_indexes)

    assert _indexes(router) == initial_indexes
