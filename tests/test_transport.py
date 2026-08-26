import pytest

from nr2301.exceptions import ProtocolError
from nr2301.transport import HTTPTransport

from conftest import FakeResponse, FakeSession


def test_single_call_without_data_uses_get():
    session = FakeSession([FakeResponse({"result": 0})])
    transport = HTTPTransport("http://192.168.1.1/", session=session, timeout=10)

    assert transport.call("version", "get_ww_version") == {"result": 0}

    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "http://192.168.1.1/api.cgi"
    assert kwargs["params"] == {
        "path": "version",
        "method": "get_ww_version",
        "timeout": "10",
    }
    assert "json" not in kwargs


def test_single_call_with_data_uses_post_json():
    session = FakeSession([FakeResponse({"result": 0})])
    transport = HTTPTransport("http://192.168.1.1", session=session)

    transport.call("account", "get_rand", data={"type": "admin", "user_id": "x"})

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["json"] == {"type": "admin", "user_id": "x"}


def test_multicall_uses_observed_outer_shape():
    session = FakeSession([FakeResponse({"responses": [{"result": 0}]})])
    transport = HTTPTransport("http://192.168.1.1", session=session)

    result = transport.multicall([
        {"path": "cm", "method": "get_cell_info", "data": {}, "timeout": 2}
    ])

    assert result == {"responses": [{"result": 0}]}
    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"] == {"multicalls": 1}
    assert kwargs["json"] == {
        "requests": [
            {"path": "cm", "method": "get_cell_info", "data": {}, "timeout": 2}
        ]
    }


def test_non_object_json_is_protocol_error():
    session = FakeSession([FakeResponse([1, 2, 3])])
    transport = HTTPTransport("http://192.168.1.1", session=session)

    with pytest.raises(ProtocolError):
        transport.call("version", "get_ww_version")


def test_multicall_accepts_any_valid_json_envelope():
    session = FakeSession([FakeResponse([{"result": 0}])])
    transport = HTTPTransport("http://192.168.1.1", session=session)

    assert transport.multicall([{"path": "version", "method": "get_ww_version"}]) == [{"result": 0}]
