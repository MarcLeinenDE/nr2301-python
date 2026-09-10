# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from ..client import NR2301Client


class PhonebookContact(TypedDict, total=False):
    index: int
    location: int
    group: int
    name: str
    mobile: str
    home: str | None
    office: str | None
    email: str


class PhonebookContactsResponse(TypedDict, total=False):
    result: int
    contactcount: int
    contactlist: list[PhonebookContact]


class PhonebookGroup(TypedDict, total=False):
    contactcount: int
    desc: str
    index: int
    name: str
    valid: int


class PhonebookGroupsResponse(TypedDict, total=False):
    result: int
    grouplist: list[PhonebookGroup]


class PhonebookWriteResponse(TypedDict, total=False):
    result: int


class PhonebookCopyResponse(TypedDict, total=False):
    result: int
    sim_count: int
    count: int
    duplicate: int
    failed: int
    invalid: int


class PhonebookNamespace:
    """Phonebook helpers backed by normalized public API evidence."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def groups(self, *, timeout: float | None = None) -> PhonebookGroupsResponse:
        """Return phonebook groups using the body-less query_group GET."""

        return cast(
            PhonebookGroupsResponse,
            self._client.call("phonebook", "query_group", timeout=timeout),
        )

    def contacts_by_location(
        self,
        location: int,
        *,
        page_capacity: int = 50,
        page_index: int = 0,
        timeout: float | None = None,
    ) -> PhonebookContactsResponse:
        """Return one raw phonebook location/page.

        Location values are intentionally left raw because the public API
        evidence has not normalized a portable SDK enum for them.
        """

        _require_nonnegative_int("location", location)
        _require_positive_int("page_capacity", page_capacity)
        _require_nonnegative_int("page_index", page_index)

        return cast(
            PhonebookContactsResponse,
            self._client.call(
                "phonebook",
                "getcontactbylocation",
                data={
                    "getcontactbylocation": {
                        "pagecap": page_capacity,
                        "pageindex": page_index,
                        "location": location,
                    }
                },
                timeout=timeout,
            ),
        )

    def contacts_by_group(
        self,
        group: int,
        *,
        page_capacity: int = 50,
        page_index: int = 0,
        timeout: float | None = None,
    ) -> PhonebookContactsResponse:
        """Return one raw contact-group page using the live-confirmed wire shape."""

        _require_nonnegative_int("group", group)
        _require_positive_int("page_capacity", page_capacity)
        _require_nonnegative_int("page_index", page_index)

        return cast(
            PhonebookContactsResponse,
            self._client.call(
                "phonebook",
                "getcontactbygroup",
                data={
                    "getcontactbygroup": {
                        "group": str(group),
                        "pagecap": str(page_capacity),
                        "pageindex": str(page_index),
                    }
                },
                timeout=timeout,
            ),
        )

    def add_group(
        self,
        name: str,
        *,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Create a phonebook group using the live-confirmed direct POST shape."""

        _require_str("name", name)
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "addnew_group",
                data={"name": name},
                timeout=timeout,
            ),
        )

    def update_group(
        self,
        index: int,
        name: str,
        *,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Rename/update one existing phonebook group."""

        _require_nonnegative_int("index", index)
        _require_str("name", name)
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "update_group",
                data={"name": name, "index": str(index)},
                timeout=timeout,
            ),
        )

    def delete_group(
        self,
        index: int,
        *,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Delete one group by index using the physically confirmed shape."""

        _require_nonnegative_int("index", index)
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "delete_group",
                data={"index": str(index)},
                timeout=timeout,
            ),
        )

    def add_contact(
        self,
        name: str,
        *,
        location: int = 0,
        mobile: str = "",
        home: str = "",
        office: str = "",
        email: str = "",
        group: int = 0,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Create a contact using the complete live-confirmed nested wire object.

        The router accepts all numeric values as strings on this write path.
        ACIY.3 create-time read-back preserves ``mobile`` and ``group`` exactly,
        while other contact fields can be normalized or omitted by firmware.
        The raw router response is returned unchanged.
        """

        _validate_contact_fields(
            location=location,
            name=name,
            mobile=mobile,
            home=home,
            office=office,
            email=email,
            group=group,
        )
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "addnew_pb",
                data={
                    "addnew_pb": {
                        "location": str(location),
                        "name": name,
                        "mobile": mobile,
                        "home": home,
                        "office": office,
                        "email": email,
                        "group": str(group),
                    }
                },
                timeout=timeout,
            ),
        )

    def update_contact(
        self,
        index: int,
        *,
        location: int = 0,
        name: str,
        mobile: str,
        home: str = "",
        office: str = "",
        email: str = "",
        group: int,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Submit the complete live-confirmed ``update_pb`` object.

        On tested firmware ACIY.3, isolated physical read-back proves ``mobile``
        and ``group`` are mutable through this endpoint. ``name``, ``home``,
        ``office`` and ``email`` are accepted with ``result=0`` but showed no
        visible update effect relative to their create-time baselines. This
        helper intentionally exposes the complete evidenced capability instead
        of hiding those fields; callers that require exact mutation semantics
        should verify the resulting contact state.
        """

        _require_nonnegative_int("index", index)
        _validate_contact_fields(
            location=location,
            name=name,
            mobile=mobile,
            home=home,
            office=office,
            email=email,
            group=group,
        )
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "update_pb",
                data={
                    "update_pb": {
                        "location": str(location),
                        "index": str(index),
                        "name": name,
                        "mobile": mobile,
                        "home": home,
                        "office": office,
                        "email": email,
                        "group": str(group),
                    }
                },
                timeout=timeout,
            ),
        )

    def delete_contact(
        self,
        index: int,
        *,
        location: int = 0,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Delete exactly one contact using the live-confirmed single-ID shape."""

        _require_nonnegative_int("index", index)
        _require_nonnegative_int("location", location)
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "delete_pb",
                data={
                    "delete_pb": {
                        "location": str(location),
                        "count": "1",
                        "indexarray": str(index),
                    }
                },
                timeout=timeout,
            ),
        )

    def move_contact_to_group(
        self,
        contact_index: int,
        group_index: int,
        *,
        timeout: float | None = None,
    ) -> PhonebookWriteResponse:
        """Move one contact to one group using the confirmed scalar-string shape."""

        _require_nonnegative_int("contact_index", contact_index)
        _require_nonnegative_int("group_index", group_index)
        return cast(
            PhonebookWriteResponse,
            self._client.call(
                "phonebook",
                "move_contacts_to_group",
                data={
                    "newgroup": str(group_index),
                    "contacts": str(contact_index),
                },
                timeout=timeout,
            ),
        )

    def copy_all_from_sim_to_local(
        self,
        *,
        timeout: float | None = None,
    ) -> PhonebookCopyResponse:
        """Copy SIM contacts to local storage using the body-less live-verified GET.

        This is state-changing even though the router exposes it as GET. Callers
        should inspect ``count``, ``duplicate``, ``failed`` and ``invalid`` rather
        than treating transport success as proof that every SIM contact copied.
        """

        return cast(
            PhonebookCopyResponse,
            self._client.call(
                "phonebook",
                "copyallfromsimtolocal",
                timeout=timeout,
            ),
        )


def _require_str(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")


def _require_nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} must be at least zero")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _validate_contact_fields(
    *,
    location: int,
    name: str,
    mobile: str,
    home: str,
    office: str,
    email: str,
    group: int,
) -> None:
    _require_nonnegative_int("location", location)
    _require_nonnegative_int("group", group)
    for field_name, value in (
        ("name", name),
        ("mobile", mobile),
        ("home", home),
        ("office", office),
        ("email", email),
    ):
        _require_str(field_name, value)
