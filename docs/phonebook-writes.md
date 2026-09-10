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

## Exact write serialization

The local-contact create/update endpoints use nested objects. Numeric values are stringified exactly as physically observed on ACIY.3.

Create:

```json
{
  "addnew_pb": {
    "location": "0",
    "name": "Example",
    "mobile": "0123456789",
    "home": "",
    "office": "",
    "email": "example@example.invalid",
    "group": "0"
  }
}
```

Update adds an `index` field inside `update_pb`. A flat update payload was physically rejected with `result=-5`.

Single-contact deletion is intentionally singular because the currently confirmed contract is:

```json
{
  "delete_pb": {
    "location": "0",
    "count": "1",
    "indexarray": "14"
  }
}
```

The multi-ID serialization is not yet established, so the SDK does not guess a plural helper.

Single-contact move is likewise the exact confirmed scalar-string representation:

```json
{
  "newgroup": "4",
  "contacts": "14"
}
```

## ACIY.3 `update_pb` semantics

A field-isolated physical campaign compared each update against the contact's actual create-time read-back, not against assumed values.

On `V1.00(ACIY.3)C0`:

- `mobile` is physically mutable;
- `group` is physically mutable;
- `name` was accepted with `result=0` but showed no visible update effect;
- `home` was accepted with `result=0` but showed no visible update effect;
- `office` was accepted with `result=0` but showed no visible update effect;
- `email` was accepted with `result=0` but showed no visible update effect.

All tests retained the same contact index and no copy-on-update row was observed. Non-target fields remained stable.

The SDK still exposes the complete evidenced `update_pb` object because it is a capability layer and firmware behavior may vary. Callers that require an exact field mutation should perform read-back rather than interpreting `result=0` as proof that every submitted field changed.

## Create-time representation caveats

The same physical campaign found that immediate local-contact read-back on ACIY.3:

- preserved `mobile` exactly as a string;
- preserved `group` exactly as an integer;
- returned `home` and `office` as `None` even when non-empty synthetic values were supplied;
- returned non-empty string values for `name` and `email`, but they were not equality-identical to the plain synthetic input strings used by the profiler.

The SDK does not invent a transformation for `name` or `email`; raw firmware values are preserved.

## SIM to local copy

`copy_all_from_sim_to_local()` mirrors the router's unusual body-less GET action. It is state-changing despite using GET. The response can report `sim_count`, `count`, `duplicate`, `failed` and `invalid`; applications should interpret those counters rather than treating HTTP success as proof that every contact was copied.

## Physical-test cleanup rule

Phonebook write tests snapshot the pre-run local-contact index set. Any new local index is treated as test-owned and cleanup is complete only after the exact original index set is restored. This is intentionally stronger than matching synthetic names because ACIY.3 can alter contact text representation.

Real names, phone numbers and SIM-contact contents must not be emitted in public logs or fixtures.
