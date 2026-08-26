import re

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


def test_sms_send_matches_verified_wire_contract_and_success_fields():
    response = {"sms": {"resp": 0, "smsSendSucc": 1, "smsSendFail": 0}}
    client, session = authenticated_client(response)

    assert client.sms.send(" +15551234567 ", "Hello\n") == response

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.send"
    sms = kwargs["json"]["sms"]
    assert sms["id"] == "-1"
    assert sms["gsm7"] == "1"
    assert sms["address"] == "+15551234567,"
    assert sms["body"] == "00480065006C006C006F"
    assert sms["protocol"] == "0"
    assert re.fullmatch(r"\d{1,2},\d{1,2},\d{1,2},\d{1,2},\d{1,2},\d{1,2},(?:%2B|-)\d+(?:\.\d+)?", sms["date"])


def test_sms_send_marks_non_gsm7_message_and_utf16_encodes_it():
    response = {"sms": {"resp": "0", "smsSendSucc": "1", "smsSendFail": "0"}}
    client, session = authenticated_client(response)

    client.sms.send("+15551234567", "Hi 😊")

    sms = session.calls[0][2]["json"]["sms"]
    assert sms["gsm7"] == "0"
    assert sms["body"] == "004800690020D83DDE0A"


def test_sms_send_rejects_unconfirmed_response():
    client, _ = authenticated_client(
        {"sms": {"resp": 0, "smsSendSucc": 0, "smsSendFail": 1}}
    )

    with pytest.raises(APIError) as exc_info:
        client.sms.send("+15551234567", "Hello")

    assert exc_info.value.method_id == "sms/sms.send"
    assert exc_info.value.response == {
        "sms": {"resp": 0, "smsSendSucc": 0, "smsSendFail": 1}
    }


def test_sms_send_validates_content_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="recipient must not be empty"):
        client.sms.send("   ", "Hello")
    with pytest.raises(ValueError, match="message must not be empty"):
        client.sms.send("+15551234567", "\n")

    assert session.calls == []


def test_sms_delete_uses_string_id_and_verified_success_triple():
    response = {"sms": {"resp": 0, "smsDelSucc": 1, "smsDelFail": 0}}
    client, session = authenticated_client(response)

    assert client.sms.delete("42") == response

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.delete"
    assert kwargs["json"] == {"sms": {"id": "42"}}


def test_sms_delete_accepts_integer_id():
    response = {"sms": {"resp": "0", "smsDelSucc": "1", "smsDelFail": "0"}}
    client, session = authenticated_client(response)

    client.sms.delete(7)

    assert session.calls[0][2]["json"] == {"sms": {"id": "7"}}


def test_sms_delete_rejects_unconfirmed_response():
    client, _ = authenticated_client(
        {"sms": {"resp": 0, "smsDelSucc": 0, "smsDelFail": 1}}
    )

    with pytest.raises(APIError) as exc_info:
        client.sms.delete(7)

    assert exc_info.value.method_id == "sms/sms.delete"


def test_sms_delete_validates_id_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="non-negative integer"):
        client.sms.delete("abc")
    with pytest.raises(TypeError, match="int or numeric str"):
        client.sms.delete(True)  # type: ignore[arg-type]

    assert session.calls == []
