from nr2301.namespaces.wifi import WiFiNamespace


def test_wifi_redaction_hides_nested_ssid_and_key():
    value = {
        "ssid": "PrivateName",
        "key": "PrivateKey",
        "channel": "6",
        "nested": {"password": "secret", "hidden": "0"},
    }
    redacted = WiFiNamespace._redact_wifi_value(value)
    assert redacted == {
        "ssid": "<redacted>",
        "key": "<redacted>",
        "channel": "6",
        "nested": {"password": "<redacted>", "hidden": "0"},
    }
