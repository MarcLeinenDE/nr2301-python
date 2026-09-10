# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import html
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, quote_plus, unquote

from nr2301 import NR2301Client


LOCAL_LOCATION = 0
PAGE_CAPACITY = 100


def _require_gate() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise SystemExit("Refusing to run without NR2301_WRITE_INTEGRATION=1")
    if os.environ.get("NR2301_PHONEBOOK_REQUIRE_EMPTY") != "1":
        raise SystemExit("Refusing to run without NR2301_PHONEBOOK_REQUIRE_EMPTY=1")


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
        raise RuntimeError("getcontactbylocation did not return a list")
    return [item for item in values if isinstance(item, Mapping)]


def _indexes(router: NR2301Client) -> set[int]:
    return {
        index
        for item in _contacts(router)
        if (index := _as_int(item.get("index"))) is not None
    }


def _find(router: NR2301Client, index: int) -> Mapping[str, Any]:
    for item in _contacts(router):
        if _as_int(item.get("index")) == index:
            return item
    raise RuntimeError(f"contact index {index} was not found")


def _classify_text(original: str, observed: object) -> list[str]:
    if not isinstance(observed, str):
        return [f"NON_STRING:{type(observed).__name__}"]

    labels: list[str] = []
    if observed == original:
        labels.append("IDENTITY")
    if observed.strip() == original and observed != original:
        labels.append("TRIMMED_WRAPPER_OR_WHITESPACE")
    if observed.lower() == original.lower() and observed != original:
        labels.append("CASE_ONLY")
    if html.unescape(observed) == original and observed != original:
        labels.append("HTML_ESCAPED")
    if unquote(observed) == original and observed != original:
        labels.append("URL_PERCENT_ENCODED")
    if original in observed and observed != original:
        labels.append("ORIGINAL_IS_SUBSTRING")

    encoded_candidates = {
        "UTF8_HEX_LOWER": original.encode("utf-8").hex(),
        "UTF8_HEX_UPPER": original.encode("utf-8").hex().upper(),
        "UTF16BE_HEX_LOWER": original.encode("utf-16-be").hex(),
        "UTF16BE_HEX_UPPER": original.encode("utf-16-be").hex().upper(),
        "UTF16LE_HEX_LOWER": original.encode("utf-16-le").hex(),
        "UTF16LE_HEX_UPPER": original.encode("utf-16-le").hex().upper(),
        "BASE64_UTF8": base64.b64encode(original.encode("utf-8")).decode("ascii"),
        "BASE64_UTF16BE": base64.b64encode(original.encode("utf-16-be")).decode("ascii"),
        "BASE64_UTF16LE": base64.b64encode(original.encode("utf-16-le")).decode("ascii"),
        "URL_QUOTE": quote(original, safe=""),
        "URL_QUOTE_PLUS": quote_plus(original, safe=""),
    }
    for label, candidate in encoded_candidates.items():
        if observed == candidate:
            labels.append(label)

    if len(observed) % 2 == 0:
        try:
            raw = bytes.fromhex(observed)
        except ValueError:
            raw = b""
        if raw:
            for encoding, label in (
                ("utf-8", "OBSERVED_HEX_DECODES_UTF8"),
                ("utf-16-be", "OBSERVED_HEX_DECODES_UTF16BE"),
                ("utf-16-le", "OBSERVED_HEX_DECODES_UTF16LE"),
            ):
                try:
                    if raw.decode(encoding) == original:
                        labels.append(label)
                except UnicodeDecodeError:
                    pass

    return labels or ["UNCLASSIFIED"]


def _describe(label: str, original: str, observed: object) -> None:
    print(f"{label}_INPUT_REPR         = {original!r}")
    print(f"{label}_OUTPUT_TYPE        = {type(observed).__name__}")
    print(f"{label}_OUTPUT_REPR        = {observed!r}")
    if isinstance(observed, str):
        print(f"{label}_INPUT_LENGTH       = {len(original)}")
        print(f"{label}_OUTPUT_LENGTH      = {len(observed)}")
        print(f"{label}_OUTPUT_CODEPOINTS  = {' '.join(f'U+{ord(ch):04X}' for ch in observed)}")
    print(f"{label}_CLASSIFICATION     = {','.join(_classify_text(original, observed))}")


def _cleanup(router: NR2301Client, initial_indexes: set[int]) -> None:
    for _ in range(3):
        extra = sorted(_indexes(router) - initial_indexes)
        if not extra:
            break
        for index in extra:
            response = router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
            print(f"CLEANUP_INDEX_{index}_RESULT = {response.get('result')!r}")
    if _indexes(router) != initial_indexes:
        raise RuntimeError("cleanup failed to restore exact initial index set")


def main() -> None:
    _require_gate()
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required")

    cases = [
        ("ASCII", "SDKTextAz09", "sdk.az09+tag@example.invalid"),
        ("SPACES", "SDK Text With Spaces", "sdk-space@example.invalid"),
        ("UNICODE", "SDK-ÄÖÜßé-€", "sdk-unicode@example.invalid"),
    ]

    with NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
        timeout=10.0,
    ) as router:
        router.login()
        initial_indexes = _indexes(router)
        print(f"INITIAL_LOCAL_CONTACT_COUNT = {len(initial_indexes)}")
        if initial_indexes:
            raise RuntimeError("preflight requires an empty local phonebook")

        successful_cases = 0
        try:
            for serial, (label, name, email) in enumerate(cases, start=1):
                before = _indexes(router)
                try:
                    response = router.phonebook.add_contact(
                        name,
                        location=LOCAL_LOCATION,
                        mobile=f"55581000{serial}",
                        home="",
                        office="",
                        email=email,
                        group=0,
                    )
                except Exception as exc:  # pragma: no cover - physical research path
                    print(f"{label}_CREATE_EXCEPTION    = {type(exc).__name__}")
                    print(f"{label}_CREATE_SUPPORTED    = False")
                    continue

                print(f"{label}_CREATE_RESULT       = {response.get('result')!r}")
                new = _indexes(router) - before
                if len(new) != 1:
                    print(f"{label}_CREATE_SUPPORTED    = False")
                    print(f"{label}_NEW_INDEX_COUNT     = {len(new)}")
                    _cleanup(router, initial_indexes)
                    continue

                successful_cases += 1
                index = next(iter(new))
                print(f"{label}_CREATE_SUPPORTED    = True")
                print(f"{label}_CONTACT_INDEX       = {index}")
                contact = _find(router, index)
                _describe(f"{label}_NAME", name, contact.get("name"))
                _describe(f"{label}_EMAIL", email, contact.get("email"))
                print(f"{label}_HOME_TYPE           = {type(contact.get('home')).__name__}")
                print(f"{label}_OFFICE_TYPE         = {type(contact.get('office')).__name__}")

                deleted = router.phonebook.delete_contact(index, location=LOCAL_LOCATION)
                print(f"{label}_DELETE_RESULT       = {deleted.get('result')!r}")
                if index in _indexes(router):
                    raise RuntimeError(f"{label}: contact cleanup failed")
        finally:
            _cleanup(router, initial_indexes)

        final_indexes = _indexes(router)
        print(f"SUCCESSFUL_CASE_COUNT       = {successful_cases}")
        print(f"FINAL_LOCAL_CONTACT_COUNT   = {len(final_indexes)}")
        print(f"FINAL_INDEX_SET_MATCH       = {final_indexes == initial_indexes}")
        if successful_cases == 0:
            raise RuntimeError("no text-representation probe created a readable contact")
        if final_indexes != initial_indexes:
            raise RuntimeError("final restore check failed")
        print("PHONEBOOK_TEXT_REPRESENTATION_PROFILER = PASS")


if __name__ == "__main__":
    main()
