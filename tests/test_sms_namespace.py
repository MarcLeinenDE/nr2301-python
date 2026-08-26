import pytest

from nr2301 import APIError, NR2301Client

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


def test_sms_brief_info_uses_live_verified_get_method():
    payload = {"new_num": 1, "unread_num": 1, "memory_full": 0}
    client, session = authenticated_client(payload)

    assert client.sms.brief_info() == payload
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "sms"
    assert kwargs["params"]["method"] == "sms.get_brief_info"


def test_sms_list_by_type_uses_documented_nested_request_shape():
    payload = {"sms": {"resp": 0, "count": 0, "total": 0, "page_count": 0}}
    client, session = authenticated_client(payload)

    assert client.sms.list_by_type(0, page_index=2) == payload
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.list_by_type"
    assert kwargs["json"] == {"sms": {"page_index": 2, "list_type": 0}}


def test_sms_list_by_type_validates_page_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="page_index must be at least 1"):
        client.sms.list_by_type(0, page_index=0)

    assert session.calls == []


def test_sms_query_ids_uses_endpoint_specific_success_rule():
    client, session = authenticated_client({"sms": {"resp": 0, "ids": "3, 7,11"}})

    ids = client.sms.query_ids(message_type=4, read=2, location=0)

    assert ids == ["3", "7", "11"]
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.query"
    assert kwargs["json"] == {"sms": {"type": 4, "read": 2, "location": 0}}


def test_sms_query_ids_raises_api_error_on_nonzero_resp():
    client, _ = authenticated_client({"sms": {"resp": -2, "ids": ""}})

    with pytest.raises(APIError) as exc_info:
        client.sms.query_ids(message_type=4, read=2, location=0)

    assert exc_info.value.method_id == "sms/sms.query"
    assert exc_info.value.response["sms"]["resp"] == -2


def test_sms_query_ids_validates_filter_types_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(TypeError, match="message_type must be an int"):
        client.sms.query_ids(message_type=True, read=2, location=0)  # type: ignore[arg-type]

    assert session.calls == []
