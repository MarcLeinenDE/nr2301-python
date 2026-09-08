# Phonebook contacts-by-group read coverage

This SDK block exposes the normalized read-only `phonebook/getcontactbygroup` contract through:

```python
client.phonebook.contacts_by_group(group, page_capacity=50, page_index=0)
```

## Wire contract

The Python helper accepts integer group/page arguments and serializes the exact ACIY.3 request shape confirmed upstream:

```json
{
  "getcontactbygroup": {
    "group": "7",
    "pagecap": "50",
    "pageindex": "0"
  }
}
```

All three nested values are strings on the wire. The response reuses `PhonebookContactsResponse` and preserves contact items without additional semantic remapping.

The helper validates numeric arguments before network access:

- `group` must be an integer and at least zero
- `page_capacity` must be an integer greater than zero
- `page_index` must be an integer and at least zero

## Physical evidence — 2026-09-08

Target: Zyxel NR2301, firmware family ACIY.3, Python 3.13.5.

A preliminary sanitized direct-call probe established the previously incomplete nested request keys and string serialization. The public-SDK targeted integration test then exercised `client.phonebook.contacts_by_group()` using a real group index selected from `query_group` and passed:

```text
tests/integration/test_readonly_router.py::test_phonebook_group_read PASSED
1 passed, 12 deselected in 0.46s
```

No group names, contact names, phone numbers or contact-list contents were printed. The selected group returned an empty list, so this run does not add new physical evidence for the field structure of non-empty contact items.

The corresponding protocol evidence is normalized upstream in `nr2301-api` PR #4.
