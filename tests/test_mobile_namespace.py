import pytest

from nr2301 import NR2301Client

from conftest import FakeResponse, FakeSession


def authenticated_client(payload):
    session = FakeSession([FakeResponse(payload)])
    session.cookies.set("CGISID", "session-123")
    client = NR2301Client(password="secret", session=session)
    client._authenticated = True
    return client, session


@pytest.mark.parametrize(
    ("helper_name", "api_method"),
    [
        ("cell_info", "get_cell_info"),
        ("wan_info", "get_current_wan_info"),
        ("available_network_modes", "get_available_network_mode"),
        ("network_settings", "get_network_settings"),
    ],
)
def test_mobile_helpers_use_live_verified_get_methods(helper_name, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.mobile, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "cm"
    assert kwargs["params"]["method"] == api_method
