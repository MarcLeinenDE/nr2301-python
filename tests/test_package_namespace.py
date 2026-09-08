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


@pytest.mark.parametrize(
    ("helper_name", "api_method"),
    [
        ("settings", "get_package_settings"),
        ("status", "get_package_status"),
    ],
)
def test_package_read_helpers_use_documented_get_methods(helper_name, api_method):
    payload = {"synthetic": True}
    client, session = authenticated_client(payload)

    helper = getattr(client.package, helper_name)
    assert helper() == payload

    method, _, kwargs = session.calls[0]
    assert method == "GET"
    assert kwargs["params"]["path"] == "package"
    assert kwargs["params"]["method"] == api_method


def test_package_settings_preserve_nested_raw_contract():
    payload = {
        "alarm_threshold": 80,
        "data_used": 123,
        "package_data_daily": {"package_data": 1000},
        "package_data_half_year": {"package_data": 2000, "start_date": "synthetic"},
        "package_data_monthly": {"package_data": 3000, "bill_day": 1},
        "package_data_one_year": {"package_data": 4000, "start_date": "synthetic"},
        "package_data_three_months": {"package_data": 5000, "start_date": "synthetic"},
        "package_data_unlimited": {"package_data": 6000},
        "package_type": "synthetic",
    }
    client, _ = authenticated_client(payload)

    assert client.package.settings() == payload


def test_package_status_preserves_documented_raw_value():
    client, _ = authenticated_client({"status": 3})

    assert client.package.status()["status"] == 3
