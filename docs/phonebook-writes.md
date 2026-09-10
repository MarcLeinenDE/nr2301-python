# Phonebook write helpers

The `client.phonebook` namespace exposes the physically evidenced NR2301 phonebook lifecycle instead of requiring direct `client.call()` usage.

## Available write surfaces

```python
client.phonebook.add_group(name)
client.phonebook.update_group(index, name)
client.phonebook.delete_group(index)

client.phonebook.add_contact(
    name,
    location=0,
    mobile="",
    home="",
    office="",
    email="",
    group=0,
)

client.phonebook.update_contact(
    index,
    location=0,
    name="...",
    mobile="...",
    home="",
    office="",
    email="",
    group=0,
)

client.phonebook.delete_contact(index, location=0)
client.phonebook.move_contact_to_group(contact_index, group_index)
client.phonebook.copy_all_from_sim_to_local()
```

Together with `groups()`, `contacts_by_location()` and `contacts_by_group()`, this gives the SDK a direct surface for all 11 currently documented methods in the upstream `phonebook` namespace.

## Contact text codec

The shipped WebUI applies `UniEncode()` to contact `name` and `email` before `addnew_pb` and `update_pb`. Each JavaScript UTF-16 code unit is serialized as four lowercase hexadecimal characters. The inverse WebUI `UniDecode()` consumes four hexadecimal characters at a time.

The SDK keeps the high-level API human-readable: `add_contact()` and `update_contact()` accept normal Python strings and internally encode only `name` and `email`. `mobile`, `home` and `office` remain plain strings. Numeric write fields remain stringified according to the observed wire contract.

Raw helpers continue to preserve router responses. For callers that need the raw codec explicitly:

```python
encoded = client.phonebook.encode_contact_text("ÄÖÜßé€2")
assert encoded == "00c400d600dc00df00e920ac0032"
assert client.phonebook.decode_contact_text(encoded) == "ÄÖÜßé€2"
```

The implementation uses Python UTF-16BE bytes, which reproduces the WebUI's per-code-unit behavior including surrogate pairs for non-BMP characters.

## Exact write serialization

The local-contact create/update endpoints use nested objects. `name` and `email` are encoded; numeric values are stringified.

Conceptual create request for human-readable `Example` / `example@example.invalid`:

```json
{
  "addnew_pb": {
    "location": "0",
    "name": "004500780061006d0070006c0065",
    "mobile": "0123456789",
    "home": "",
    "office": "",
    "email": "006500780061006d0070006c00650040006500780061006d0070006c0065002e0069006e00760061006c00690064",
    "group": "0"
  }
}
```

Update adds an `index` field inside `update_pb`. A flat update payload was physically rejected with `result=-5`.

Single-contact deletion remains intentionally singular because the physically confirmed SDK helper sends:

```json
{
  "delete_pb": {
    "location": "0",
    "count": "1",
    "indexarray": "14"
  }
}
```

Related backend source splits `indexarray` on commas, strongly supporting a comma-separated plural representation; physical NR2301 multi-delete validation is tracked separately before a plural helper is frozen.

Single-contact move is the exact confirmed scalar-string representation:

```json
{
  "newgroup": "4",
  "contacts": "14"
}
```

## ACIY.3 create/update semantics after codec correction

The earlier plaintext-name/email probes did not match the shipped WebUI application-level wire contract and are superseded by the codec-corrected physical test.

On `V1.00(ACIY.3)C0`, a synthetic contact created through the corrected high-level SDK produced:

- `result=0`;
- one new local index;
- raw `name` exactly equal to the SDK/WebUI encoding;
- decoded `name` exactly equal to the submitted human-readable name;
- exact `mobile` read-back;
- encoded `email` accepted but local read-back remained the literal string `"-"`;
- non-empty `home` and `office` accepted but local read-back remained `None`.

The same contact was then updated in place with Unicode name `ÄÖÜßé€2` and new values. Physical read-back showed:

- same contact index retained — no copy-on-update row;
- raw `name` exactly `00c400d600dc00df00e920ac0032`;
- decoded `name` exactly `ÄÖÜßé€2`;
- `mobile` changed to the requested value;
- correctly encoded `email` still read back as `"-"`, unchanged from create baseline;
- `home` remained `None`;
- `office` remained `None`.

Combined with the earlier isolated group-field test, the physically demonstrated read-back-visible mutable fields are therefore `name`, `mobile` and `group`. `email`, `home` and `office` remain accepted wire fields but their submitted values are not exposed through the tested local-contact read path on ACIY.3.

Applications should still use read-back when mutation visibility matters instead of interpreting `result=0` as proof that every submitted field became observable.

## SIM to local copy

`copy_all_from_sim_to_local()` mirrors the router's unusual body-less GET action. It is state-changing despite using GET. The response can report `sim_count`, `count`, `duplicate`, `failed` and `invalid`; applications should interpret those counters rather than treating HTTP success as proof that every contact was copied.

## Physical-test cleanup rule

Phonebook write tests snapshot the pre-run local-contact index set. Any new local index is treated as test-owned and cleanup is complete only after the exact original index set is restored. This is intentionally stronger than matching synthetic names.

Real names, phone numbers and SIM-contact contents must not be emitted in public logs or fixtures.

## Physical validation

The initial public high-level write surface was physically validated on 2026-09-10 against firmware `V1.00(ACIY.3)C0` using Python 3.13.5.

`tests/integration/test_phonebook_writes.py` passed **2/2 tests in 4.32 s**:

- `test_phonebook_high_level_write_lifecycle_and_restore` created/renamed groups, created one synthetic local contact, changed `mobile` and `group`, moved the contact, deleted the contact/groups, and restored the exact initial local-contact index set.
- `test_copy_all_from_sim_to_local_and_restore_local_index_set` exercised `copy_all_from_sim_to_local()` without modifying SIM storage, treated only newly created local indexes as test-owned, removed those local rows, and restored the exact initial local-contact index set.

The codec-correction test `tests/integration/test_phonebook_text_codec.py` later passed **1/1 in 1.02 s**. It physically confirmed WebUI-compatible name create/update behavior including Unicode, characterized email/home/office read-back as above, deleted the synthetic contact, and ended with `FINAL_LOCAL_CONTACT_COUNT = 0` and `FINAL_INDEX_SET_MATCH = True`.

No real contact names, phone numbers or SIM-contact contents were printed or committed during this validation.
