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


class PhonebookNamespace:
    """Phonebook helpers backed by normalized public API evidence.

    Only source-complete request contracts are exposed as high-level helpers.
    The generic client call() remains available for other documented methods
    until their nested write payloads are normalized.
    """

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
        evidence has not yet normalized a portable SDK enum for them.
        """

        for name, value in (
            ("location", location),
            ("page_capacity", page_capacity),
            ("page_index", page_index),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")
        if page_capacity <= 0:
            raise ValueError("page_capacity must be greater than zero")
        if page_index < 0:
            raise ValueError("page_index must be at least zero")

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
