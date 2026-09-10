import pytest

from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(*payloads):
    responses = [
        payload if isinstance(payload, FakeResponse) else FakeResponse(payload)
        for payload in payloads
    ]
    session = FakeSession(responses)
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def assert_call(session, *, http_method, api_method, data=None):
    method, _, kwargs = session.calls[0]
    assert method == http_method
    assert kwargs["params"]["path"] == "phonebook"
    assert kwargs["params"]["method"] == api_method
    if data is None:
        assert "json" not in kwargs
    else:
        assert kwargs["json"] == data


def test_groups_uses_bodyless_query_group_get():
    payload = {"result": 0, "grouplist": []}
    client, session = authenticated_client(payload)

    assert client.phonebook.groups() == payload
    assert_call(session, http_method="GET", api_method="query_group")


def test_contacts_by_location_uses_exact_documented_payload():
    payload = {"result": 0, "contactcount": 0, "contactlist": []}
    client, session = authenticated_client(payload)

    assert client.phonebook.contacts_by_location(
        0,
        page_capacity=50,
        page_index=0,
    ) == payload

    assert_call(
        session,
        http_method="POST",
        api_method="getcontactbylocation",
        data={
            "getcontactbylocation": {
                "pagecap": 50,
                "pageindex": 0,
                "location": 0,
            }
        },
    )


def test_contacts_by_location_validates_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="location must be an int"):
        client.phonebook.contacts_by_location(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="greater than zero"):
        client.phonebook.contacts_by_location(0, page_capacity=0)
    with pytest.raises(ValueError, match="at least zero"):
        client.phonebook.contacts_by_location(0, page_index=-1)

    assert session.calls == []


def test_contacts_by_group_uses_live_confirmed_string_payload():
    payload = {"result": 0, "contactcount": 0, "contactlist": []}
    client, session = authenticated_client(payload)

    assert client.phonebook.contacts_by_group(
        7,
        page_capacity=50,
        page_index=2,
    ) == payload

    assert_call(
        session,
        http_method="POST",
        api_method="getcontactbygroup",
        data={
            "getcontactbygroup": {
                "group": "7",
                "pagecap": "50",
                "pageindex": "2",
            }
        },
    )


def test_contacts_by_group_validates_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="group must be an int"):
        client.phonebook.contacts_by_group(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="group must be at least zero"):
        client.phonebook.contacts_by_group(-1)
    with pytest.raises(ValueError, match="greater than zero"):
        client.phonebook.contacts_by_group(0, page_capacity=0)
    with pytest.raises(ValueError, match="at least zero"):
        client.phonebook.contacts_by_group(0, page_index=-1)

    assert session.calls == []


def test_add_group_uses_exact_live_confirmed_payload():
    payload = {"result": 0, "future": "preserved"}
    client, session = authenticated_client(payload)

    assert client.phonebook.add_group("SDK group") == payload
    assert_call(
        session,
        http_method="POST",
        api_method="addnew_group",
        data={"name": "SDK group"},
    )


def test_update_group_stringifies_index():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.phonebook.update_group(7, "Renamed") == payload
    assert_call(
        session,
        http_method="POST",
        api_method="update_group",
        data={"name": "Renamed", "index": "7"},
    )


def test_delete_group_stringifies_index():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.phonebook.delete_group(7) == payload
    assert_call(
        session,
        http_method="POST",
        api_method="delete_group",
        data={"index": "7"},
    )


def test_add_contact_uses_complete_nested_string_payload():
    payload = {"result": 0, "unknown": {"kept": True}}
    client, session = authenticated_client(payload)

    assert client.phonebook.add_contact(
        "Synthetic",
        location=0,
        mobile="5550100001",
        home="5550200001",
        office="5550300001",
        email="synthetic@example.invalid",
        group=4,
    ) == payload

    assert_call(
        session,
        http_method="POST",
        api_method="addnew_pb",
        data={
            "addnew_pb": {
                "location": "0",
                "name": "Synthetic",
                "mobile": "5550100001",
                "home": "5550200001",
                "office": "5550300001",
                "email": "synthetic@example.invalid",
                "group": "4",
            }
        },
    )


def test_update_contact_uses_complete_nested_string_payload():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.phonebook.update_contact(
        8,
        location=0,
        name="Synthetic",
        mobile="5551100001",
        home="",
        office="",
        email="synthetic@example.invalid",
        group=5,
    ) == payload

    assert_call(
        session,
        http_method="POST",
        api_method="update_pb",
        data={
            "update_pb": {
                "location": "0",
                "index": "8",
                "name": "Synthetic",
                "mobile": "5551100001",
                "home": "",
                "office": "",
                "email": "synthetic@example.invalid",
                "group": "5",
            }
        },
    )


def test_delete_contact_uses_physically_confirmed_single_id_shape():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.phonebook.delete_contact(9, location=0) == payload
    assert_call(
        session,
        http_method="POST",
        api_method="delete_pb",
        data={
            "delete_pb": {
                "location": "0",
                "count": "1",
                "indexarray": "9",
            }
        },
    )


def test_move_contact_to_group_uses_scalar_strings():
    payload = {"result": 0}
    client, session = authenticated_client(payload)

    assert client.phonebook.move_contact_to_group(9, 5) == payload
    assert_call(
        session,
        http_method="POST",
        api_method="move_contacts_to_group",
        data={"newgroup": "5", "contacts": "9"},
    )


def test_copy_all_from_sim_to_local_is_bodyless_get_and_preserves_counts():
    payload = {
        "result": 0,
        "sim_count": 11,
        "count": 0,
        "duplicate": 11,
        "failed": 0,
        "invalid": 0,
    }
    client, session = authenticated_client(payload)

    assert client.phonebook.copy_all_from_sim_to_local() == payload
    assert_call(session, http_method="GET", api_method="copyallfromsimtolocal")


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda ns: ns.add_group(123), "name must be a str"),  # type: ignore[arg-type]
        (lambda ns: ns.update_group(True, "x"), "index must be an int"),  # type: ignore[arg-type]
        (lambda ns: ns.delete_group(-1), "index must be at least zero"),
        (
            lambda ns: ns.add_contact("x", location=True),  # type: ignore[arg-type]
            "location must be an int",
        ),
        (
            lambda ns: ns.add_contact("x", mobile=123),  # type: ignore[arg-type]
            "mobile must be a str",
        ),
        (
            lambda ns: ns.update_contact(
                1,
                name="x",
                mobile="1",
                group=-1,
            ),
            "group must be at least zero",
        ),
        (lambda ns: ns.delete_contact(True), "index must be an int"),  # type: ignore[arg-type]
        (
            lambda ns: ns.move_contact_to_group(1, True),  # type: ignore[arg-type]
            "group_index must be an int",
        ),
    ],
)
def test_write_helpers_validate_before_network_access(call, message):
    client, session = authenticated_client()

    with pytest.raises((TypeError, ValueError), match=message):
        call(client.phonebook)

    assert session.calls == []
