# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_INTEGRATION") != "1":
    pytest.skip(
        "physical Phonebook read-only test requires NR2301_INTEGRATION=1",
        allow_module_level=True,
    )


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


def _field_union(items: object) -> str:
    if not isinstance(items, list):
        pytest.fail("Phonebook list field was not a list")
    fields: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            pytest.fail("Phonebook list contained a non-object item")
        fields.update(str(key) for key in item.keys())
    return ",".join(sorted(fields)) if fields else "-"


def test_phonebook_readonly_groups_and_local_location() -> None:
    router = _client()
    try:
        groups = router.phonebook.groups()
        group_list = groups.get("grouplist", [])
        if not isinstance(group_list, list):
            pytest.fail("query_group grouplist was not a list")
        print(
            "PHONEBOOK_GROUPS "
            f"result={groups.get('result')} count={len(group_list)} "
            f"fields={_field_union(group_list)}"
        )

        contacts = router.phonebook.contacts_by_location(
            0,
            page_capacity=50,
            page_index=0,
        )
        contact_list = contacts.get("contactlist", [])
        if not isinstance(contact_list, list):
            pytest.fail("getcontactbylocation contactlist was not a list")
        print(
            "PHONEBOOK_CONTACTS location=0 "
            f"result={contacts.get('result')} "
            f"contactcount={contacts.get('contactcount')} "
            f"returned_count={len(contact_list)} "
            f"fields={_field_union(contact_list)}"
        )
    finally:
        router.close()
