# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client


if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "phonebook codec test requires NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )

if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") != "1":
    pytest.skip(
        "phonebook codec test requires NR2301_PHONEBOOK_REQUIRE_EMPTY=1",
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


def _find(router: NR2301Client, index: int) -> Mapping[str, object]:
    for item in _contacts(router):
        if _as_int(item.get("index")) == index:
            return item
    raise AssertionError(f"contact index {index} not found")


def _decode(router: NR2301Client, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return router.phonebook.decode_contact_text(value)
    except ValueError:
        return None


def _field_state(actual: object, target: str, baseline: object) -> str:
    if actual == target:
        return "PLAIN_TARGET"
    if actual == baseline:
        return "UNCHANGED_FROM_BASELINE"
    if actual is None:
        return "NONE"
    if actual == "-":
        return "DASH_SENTINEL"
    return "OTHER"


def test_phonebook_text_codec_and_remaining_fields(router=None):
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
        assert not initial_indexes, "preflight requires an empty local phonebook"

        created_index: int | None = None
        create_name = "CodecA1"
        create_email = "codec-a1@example.invalid"
        create_mobile = "5559100001"
        create_home = "5559200001"
        create_office = "5559300001"

        update_name = "ÄÖÜßé€2"
        update_email = "codec-b2@example.invalid"
        update_mobile = "5559100002"
        update_home = "5559200002"
        update_office = "5559300002"

        try:
            response = client.phonebook.add_contact(
                create_name,
                location=LOCAL_LOCATION,
                mobile=create_mobile,
                home=create_home,
                office=create_office,
                email=create_email,
                group=0,
            )
            print("CREATE_RESULT              =", response.get("result"))
            assert response.get("result") == 0

            created = _indexes(client) - initial_indexes
            assert len(created) == 1
            created_index = next(iter(created))
            print("CREATE_INDEX               =", created_index)

            item = _find(client, created_index)
            create_raw_name = item.get("name")
            create_raw_email = item.get("email")
            create_home_observed = item.get("home")
            create_office_observed = item.get("office")

            print("CREATE_NAME_RAW_MATCH      =", create_raw_name == client.phonebook.encode_contact_text(create_name))
            print("CREATE_NAME_DECODE_MATCH   =", _decode(client, create_raw_name) == create_name)
            print("CREATE_EMAIL_RAW_REPR      =", repr(create_raw_email))
            print("CREATE_EMAIL_RAW_MATCH     =", create_raw_email == client.phonebook.encode_contact_text(create_email))
            print("CREATE_EMAIL_DECODE_MATCH  =", _decode(client, create_raw_email) == create_email)
            print("CREATE_MOBILE_MATCH        =", item.get("mobile") == create_mobile)
            print("CREATE_HOME_REPR           =", repr(create_home_observed))
            print("CREATE_HOME_MATCH          =", create_home_observed == create_home)
            print("CREATE_OFFICE_REPR         =", repr(create_office_observed))
            print("CREATE_OFFICE_MATCH        =", create_office_observed == create_office)

            # The WebUI-derived codec itself must round-trip for name. The
            # remaining fields are characterization targets and must not abort
            # the update half of this physical probe.
            assert create_raw_name == client.phonebook.encode_contact_text(create_name)
            assert _decode(client, create_raw_name) == create_name
            assert item.get("mobile") == create_mobile

            response = client.phonebook.update_contact(
                created_index,
                location=LOCAL_LOCATION,
                name=update_name,
                mobile=update_mobile,
                home=update_home,
                office=update_office,
                email=update_email,
                group=0,
            )
            print("UPDATE_RESULT              =", response.get("result"))
            assert response.get("result") == 0

            updated = _find(client, created_index)
            update_raw_name = updated.get("name")
            update_raw_email = updated.get("email")
            update_home_observed = updated.get("home")
            update_office_observed = updated.get("office")

            print("UPDATE_SAME_INDEX          =", _as_int(updated.get("index")) == created_index)
            print("UPDATE_NAME_RAW_REPR       =", repr(update_raw_name))
            print("UPDATE_NAME_RAW_MATCH      =", update_raw_name == client.phonebook.encode_contact_text(update_name))
            print("UPDATE_NAME_DECODE_MATCH   =", _decode(client, update_raw_name) == update_name)
            print("UPDATE_EMAIL_RAW_REPR      =", repr(update_raw_email))
            print("UPDATE_EMAIL_RAW_MATCH     =", update_raw_email == client.phonebook.encode_contact_text(update_email))
            print("UPDATE_EMAIL_DECODE_MATCH  =", _decode(client, update_raw_email) == update_email)
            print("UPDATE_EMAIL_STATE         =", _field_state(update_raw_email, client.phonebook.encode_contact_text(update_email), create_raw_email))
            print("UPDATE_MOBILE_MATCH        =", updated.get("mobile") == update_mobile)
            print("UPDATE_HOME_REPR           =", repr(update_home_observed))
            print("UPDATE_HOME_MATCH          =", update_home_observed == update_home)
            print("UPDATE_HOME_STATE          =", _field_state(update_home_observed, update_home, create_home_observed))
            print("UPDATE_OFFICE_REPR         =", repr(update_office_observed))
            print("UPDATE_OFFICE_MATCH        =", update_office_observed == update_office)
            print("UPDATE_OFFICE_STATE        =", _field_state(update_office_observed, update_office, create_office_observed))

            assert _as_int(updated.get("index")) == created_index
            assert update_raw_name == client.phonebook.encode_contact_text(update_name)
            assert _decode(client, update_raw_name) == update_name
            assert updated.get("mobile") == update_mobile
        finally:
            for index in sorted(_indexes(client) - initial_indexes):
                cleanup = client.phonebook.delete_contact(index, location=LOCAL_LOCATION)
                print(f"CLEANUP_INDEX_{index}_RESULT =", cleanup.get("result"))
                assert cleanup.get("result") == 0

            final_indexes = _indexes(client)
            print("FINAL_LOCAL_CONTACT_COUNT  =", len(final_indexes))
            print("FINAL_INDEX_SET_MATCH      =", final_indexes == initial_indexes)
            assert final_indexes == initial_indexes
