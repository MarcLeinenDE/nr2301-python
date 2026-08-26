from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(payload):
    session = FakeSession([FakeResponse(payload)])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


def test_version_info_uses_live_verified_get_method():
    payload = {"result": 0, "hw_ver": "MIFI.NR2301.H01", "sw_ver": "V1.00(TEST)"}
    client, session = authenticated_client(payload)

    assert client.version.info() == payload
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "version"
    assert kwargs["params"]["method"] == "get_ww_version"


def test_magic_number_uses_live_verified_get_method():
    payload = {"result": 0, "magic": "synthetic-value"}
    client, session = authenticated_client(payload)

    assert client.version.magic_number() == payload
    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["method"] == "get_magicnumber"
