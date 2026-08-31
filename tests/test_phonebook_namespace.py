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


def test_groups_uses_bodyless_query_group_get():
    payload = {"result": 0, "grouplist": []}
    client, session = authenticated_client(payload)

    assert client.phonebook.groups() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "phonebook"
    assert kwargs["params"]["method"] == "query_group"
    assert "json" not in kwargs


def test_contacts_by_location_uses_exact_documented_payload():
    payload = {"result": 0, "contactcount": 0, "contactlist": []}
    client, session = authenticated_client(payload)

    assert client.phonebook.contacts_by_location(
        0,
        page_capacity=50,
        page_index=0,
    ) == payload

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "phonebook"
    assert kwargs["params"]["method"] == "getcontactbylocation"
    assert kwargs["json"] == {
        "getcontactbylocation": {
            "pagecap": 50,
            "pageindex": 0,
            "location": 0,
        }
    }


def test_contacts_by_location_validates_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="location must be an int"):
        client.phonebook.contacts_by_location(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="greater than zero"):
        client.phonebook.contacts_by_location(0, page_capacity=0)
    with pytest.raises(ValueError, match="at least zero"):
        client.phonebook.contacts_by_location(0, page_index=-1)

    assert session.calls == []
