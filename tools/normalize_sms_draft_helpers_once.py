# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

SMS = Path('src/nr2301/namespaces/sms.py')
TESTS = Path('tests/test_sms_namespace.py')
CHANGELOG = Path('CHANGELOG.md')

text = SMS.read_text(encoding='utf-8')

class_anchor = '''class SMSDeleteResponse(TypedDict, total=False):\n    sms: SMSDeleteResult\n\n\n'''
class_block = '''class SMSDeleteResponse(TypedDict, total=False):\n    sms: SMSDeleteResult\n\n\nclass SMSGetByIdMessage(TypedDict, total=False):\n    address: str\n    body: str\n    contact_id: int\n    date: str\n    id: int\n    location: int\n    protocol: int\n    read: int\n    resp: int\n    status: int\n    type: int\n\n\nclass SMSGetByIdResponse(TypedDict, total=False):\n    sms: SMSGetByIdMessage\n\n\nclass SMSSaveResult(TypedDict, total=False):\n    resp: int\n    smsSaveSucc: int\n    smsSaveFail: int\n\n\nclass SMSSaveResponse(TypedDict, total=False):\n    sms: SMSSaveResult\n\n\n'''
if 'class SMSSaveResult' not in text:
    if class_anchor not in text:
        raise SystemExit('class anchor not found')
    text = text.replace(class_anchor, class_block, 1)

method_anchor = '    def send(\n'
methods = '''    def get_by_id(\n        self,\n        message_id: int | str,\n        *,\n        timeout: float | None = None,\n    ) -> SMSGetByIdResponse:\n        \"\"\"Return one SMS by ID using the exact nested request contract.\n\n        Reading an unread inbound message may mark it read on the router. The\n        helper therefore performs no hidden retries or follow-up reads.\n        \"\"\"\n\n        id_text = _message_id_text(message_id, allow_new=False)\n        response = self._client.call(\n            \"sms\",\n            \"sms.get_by_id\",\n            data={\"sms\": {\"id\": id_text}},\n            timeout=timeout,\n        )\n        self._extract_sms(response, method_id=\"sms/sms.get_by_id\")\n        return cast(SMSGetByIdResponse, response)\n\n    def save_draft(\n        self,\n        recipient: str,\n        message: str,\n        *,\n        message_id: int | str = -1,\n        timeout: float = 100.0,\n    ) -> SMSSaveResponse:\n        \"\"\"Create or update a normal-protocol SMS draft.\n\n        The exact live-verified draft contract uses type=2 and protocol=0.\n        `message_id=-1` creates a new draft; an existing non-negative ID\n        updates that draft. Recipient/message values are never included in\n        SDK-generated error metadata.\n        \"\"\"\n\n        if not isinstance(recipient, str):\n            raise TypeError(\"recipient must be a str\")\n        if not isinstance(message, str):\n            raise TypeError(\"message must be a str\")\n        if timeout <= 0:\n            raise ValueError(\"timeout must be greater than zero\")\n\n        recipient = recipient.strip()\n        if not recipient:\n            raise ValueError(\"recipient must not be empty\")\n        if not message:\n            raise ValueError(\"message must not be empty\")\n\n        id_text = _message_id_text(message_id, allow_new=True)\n        payload = {\n            \"sms\": {\n                \"id\": id_text,\n                \"gsm7\": _is_gsm7(message),\n                \"address\": recipient.rstrip(\",\") + \",\",\n                \"body\": _uni_encode(message),\n                \"date\": _sms_time(encode_plus=False),\n                \"type\": \"2\",\n                \"protocol\": \"0\",\n            }\n        }\n        response = self._client.call(\n            \"sms\",\n            \"sms.save\",\n            data=payload,\n            timeout=timeout,\n        )\n        sms = self._extract_sms(response, method_id=\"sms/sms.save\")\n        if not (\n            _int_equals(sms.get(\"resp\"), 0)\n            and _int_equals(sms.get(\"smsSaveSucc\"), 1)\n            and _int_equals(sms.get(\"smsSaveFail\"), 0)\n        ):\n            raise APIError(\n                \"sms/sms.save did not report verified draft-save success\",\n                method_id=\"sms/sms.save\",\n                response=_redact_sms_save_response(response),\n            )\n        return cast(SMSSaveResponse, response)\n\n'''
if '    def save_draft(' not in text:
    if method_anchor not in text:
        raise SystemExit('method anchor not found')
    text = text.replace(method_anchor, methods + method_anchor, 1)

old_time = '''def _sms_time(now: dt.datetime | None = None) -> str:\n    \"\"\"Match the observed frontend GetSmsTime string.\"\"\"\n\n    current = now.astimezone() if now is not None else dt.datetime.now().astimezone()\n    offset = current.utcoffset() or dt.timedelta()\n    hours = offset.total_seconds() / 3600.0\n    if abs(hours - round(hours)) < 1e-9:\n        off = str(abs(int(round(hours))))\n    else:\n        off = str(abs(hours)).rstrip(\"0\").rstrip(\".\")\n    timezone = (\"%2B\" if hours >= 0 else \"-\") + off\n    return (\n        f\"{current.year % 100},{current.month},{current.day},\"\n        f\"{current.hour},{current.minute},{current.second},{timezone}\"\n    )\n'''
new_time = '''def _sms_time(\n    now: dt.datetime | None = None,\n    *,\n    encode_plus: bool = True,\n) -> str:\n    \"\"\"Match the observed frontend GetSmsTime variants.\n\n    Normal SMS send is live verified with an encoded positive sign (`%2B`),\n    while historical live draft-save evidence captured a literal `+`.\n    \"\"\"\n\n    current = now.astimezone() if now is not None else dt.datetime.now().astimezone()\n    offset = current.utcoffset() or dt.timedelta()\n    hours = offset.total_seconds() / 3600.0\n    if abs(hours - round(hours)) < 1e-9:\n        off = str(abs(int(round(hours))))\n    else:\n        off = str(abs(hours)).rstrip(\"0\").rstrip(\".\")\n    positive = \"%2B\" if encode_plus else \"+\"\n    timezone = (positive if hours >= 0 else \"-\") + off\n    return (\n        f\"{current.year % 100},{current.month},{current.day},\"\n        f\"{current.hour},{current.minute},{current.second},{timezone}\"\n    )\n'''
if 'encode_plus: bool = True' not in text:
    if old_time not in text:
        raise SystemExit('time helper anchor not found')
    text = text.replace(old_time, new_time, 1)

helper_anchor = '\ndef _int_equals(value: Any, expected: int) -> bool:\n'
helper = '''\ndef _message_id_text(message_id: int | str, *, allow_new: bool) -> str:\n    if isinstance(message_id, bool) or not isinstance(message_id, (int, str)):\n        raise TypeError(\"message_id must be an int or numeric str\")\n    id_text = str(message_id).strip()\n    if allow_new and id_text == \"-1\":\n        return id_text\n    if not id_text.isdigit():\n        expectation = \"-1 or a non-negative integer\" if allow_new else \"a non-negative integer\"\n        raise ValueError(f\"message_id must be {expectation}\")\n    return id_text\n\n'''
if 'def _message_id_text(' not in text:
    if helper_anchor not in text:
        raise SystemExit('id helper anchor not found')
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

redact_anchor = '\ndef _redact_sms_response(response: Mapping[str, Any]) -> dict[str, Any]:\n'
redact = '''\ndef _redact_sms_save_response(response: Mapping[str, Any]) -> dict[str, Any]:\n    \"\"\"Keep only non-content draft-save status fields in error details.\"\"\"\n\n    sms = response.get(\"sms\")\n    if not isinstance(sms, Mapping):\n        return {\"sms\": \"invalid response object\"}\n    return {\n        \"sms\": {\n            key: sms.get(key)\n            for key in (\"resp\", \"smsSaveSucc\", \"smsSaveFail\")\n            if key in sms\n        }\n    }\n\n'''
if 'def _redact_sms_save_response(' not in text:
    if redact_anchor not in text:
        raise SystemExit('redaction anchor not found')
    text = text.replace(redact_anchor, redact + redact_anchor, 1)

SMS.write_text(text, encoding='utf-8')

tests = TESTS.read_text(encoding='utf-8')
addition = r'''


def test_sms_get_by_id_uses_exact_nested_string_id_contract():
    response = {"sms": {"resp": 0, "id": 42, "type": 2, "body": "0041"}}
    client, session = authenticated_client(response)

    assert client.sms.get_by_id(42) == response

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.get_by_id"
    assert kwargs["json"] == {"sms": {"id": "42"}}


def test_sms_get_by_id_validates_id_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="non-negative integer"):
        client.sms.get_by_id("-1")
    with pytest.raises(TypeError, match="int or numeric str"):
        client.sms.get_by_id(True)  # type: ignore[arg-type]

    assert session.calls == []


def test_sms_save_draft_matches_historical_live_wire_contract():
    response = {"sms": {"resp": 0, "smsSaveSucc": 1, "smsSaveFail": 0}}
    client, session = authenticated_client(response)

    assert client.sms.save_draft(" 0000000000 ", "Draft") == response

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["method"] == "sms.save"
    sms = kwargs["json"]["sms"]
    assert sms["id"] == "-1"
    assert sms["gsm7"] is True
    assert sms["address"] == "0000000000,"
    assert sms["body"] == "00440072006100660074"
    assert sms["type"] == "2"
    assert sms["protocol"] == "0"
    assert re.fullmatch(r"\d{1,2},\d{1,2},\d{1,2},\d{1,2},\d{1,2},\d{1,2},(?:\+|-)\d+(?:\.\d+)?", sms["date"])


def test_sms_save_draft_updates_existing_id_and_preserves_gsm7_boolean():
    response = {"sms": {"resp": "0", "smsSaveSucc": "1", "smsSaveFail": "0"}}
    client, session = authenticated_client(response)

    client.sms.save_draft("0000000000", "Hi 😊", message_id="42")

    sms = session.calls[0][2]["json"]["sms"]
    assert sms["id"] == "42"
    assert sms["gsm7"] is False
    assert sms["body"] == "004800690020D83DDE0A"


def test_sms_save_draft_rejects_unconfirmed_response_without_content_leak():
    client, _ = authenticated_client(
        {"sms": {"resp": 0, "smsSaveSucc": 0, "smsSaveFail": 1, "body": "secret"}}
    )

    with pytest.raises(APIError) as exc_info:
        client.sms.save_draft("0000000000", "private draft")

    assert exc_info.value.method_id == "sms/sms.save"
    assert exc_info.value.response == {
        "sms": {"resp": 0, "smsSaveSucc": 0, "smsSaveFail": 1}
    }


def test_sms_save_draft_validates_inputs_before_network_access():
    client, session = authenticated_client()

    with pytest.raises(ValueError, match="recipient must not be empty"):
        client.sms.save_draft("   ", "Draft")
    with pytest.raises(ValueError, match="message must not be empty"):
        client.sms.save_draft("0000000000", "")
    with pytest.raises(ValueError, match="-1 or a non-negative integer"):
        client.sms.save_draft("0000000000", "Draft", message_id="abc")

    assert session.calls == []
'''
if 'test_sms_save_draft_matches_historical_live_wire_contract' not in tests:
    tests = tests.rstrip() + addition + '\n'
TESTS.write_text(tests, encoding='utf-8')

changelog = CHANGELOG.read_text(encoding='utf-8')
entry = '- added `client.sms.get_by_id()` and `client.sms.save_draft()` from normalized public contracts; draft create/update preserves the historically live-verified wire distinction (string id/type/protocol, boolean gsm7), enforces the save success triple, and redacts message content from SDK-generated errors\n'
marker = '## Unreleased\n\n'
if entry not in changelog and marker in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
CHANGELOG.write_text(changelog, encoding='utf-8')

print('Normalized SMS draft/get-by-id SDK helpers and tests.')
