import requests

from nr2301.transport import HTTPTransport

from conftest import FakeResponse, FakeSession


def test_file_download_uses_authenticated_file_cgi_get_and_returns_bytes():
    session = FakeSession([FakeResponse(content=b"CONFIG-BYTES")])
    session.cookies.set("CGISID", "session-123")
    transport = HTTPTransport("http://router.test", session=session)

    result = transport.file_download(
        params={"Action": "Download", "file": "backup_config", "dl": "1"},
        timeout=7.5,
    )

    assert result == b"CONFIG-BYTES"
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "http://router.test/file.cgi"
    assert kwargs["params"] == {
        "Action": "Download",
        "file": "backup_config",
        "dl": "1",
    }
    assert kwargs["timeout"] == 7.5
    assert "json" not in kwargs
    assert "data" not in kwargs


def test_file_upload_posts_raw_octet_stream_without_multipart_or_range_headers():
    session = FakeSession([FakeResponse(content=b"OK")])
    transport = HTTPTransport("http://router.test", session=session)

    result = transport.file_upload(
        b"\x00\x01\xffCONFIG",
        params={"Action": "Upload", "file": "restore_config"},
        timeout=9,
    )

    assert result == b"OK"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "http://router.test/file.cgi"
    assert kwargs["params"] == {
        "Action": "Upload",
        "file": "restore_config",
    }
    assert kwargs["data"] == b"\x00\x01\xffCONFIG"
    assert kwargs["headers"] == {"Content-Type": "application/octet-stream"}
    assert "files" not in kwargs
    assert "json" not in kwargs
    assert "Content-Range" not in kwargs["headers"]


def test_file_transport_wraps_requests_errors():
    session = FakeSession([requests.ConnectionError("gone")])
    transport = HTTPTransport("http://router.test", session=session)

    from nr2301 import TransportError

    try:
        transport.file_download(params={"Action": "Download"})
    except TransportError:
        pass
    else:
        raise AssertionError("TransportError not raised")
