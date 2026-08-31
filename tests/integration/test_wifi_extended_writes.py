# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import os
from collections.abc import Mapping

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical extended Wi-Fi tests require NR2301_WRITE_INTEGRATION=1",
        allow_module_level=True,
    )


def _client() -> NR2301Client:
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        pytest.skip("NR2301_PASSWORD is required for physical-router integration tests")
    router = NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
    )
    router.login()
    return router


def _config(router: NR2301Client) -> dict:
    response = router.wifi.config()
    config = response.get("config")
    assert isinstance(config, dict)
    return config


_NON_CONFIG_FIELDS = {
    "wifi_if_24G": {"cur_channel", "first_channel", "last_channel"},
    "wifi_if_5G": {"cur_channel", "channel_list"},
}


def _configurable_view(section: str, block: dict) -> dict:
    ignored = _NON_CONFIG_FIELDS.get(section, set())
    return {key: value for key, value in block.items() if key not in ignored}


def _mismatched_fields(actual: dict, expected: dict) -> list[str]:
    return sorted(
        key
        for key in set(actual) | set(expected)
        if actual.get(key) != expected.get(key)
    )


def _restore_section(router: NR2301Client, section: str, original: dict) -> None:
    expected = _configurable_view(section, original)
    current = _config(router).get(section)
    if not isinstance(current, dict):
        pytest.fail(f"{section} restore current state returned no mapping")
    if _configurable_view(section, current) != expected:
        router.wifi.update_ap_section(section, expected)
    final = _config(router).get(section)
    if not isinstance(final, dict):
        pytest.fail(f"{section} restore returned no mapping")
    final_view = _configurable_view(section, final)
    if final_view != expected:
        # Runtime/capability fields such as cur_channel are deliberately not
        # restore targets. Only mutable configuration differences are reported.
        pytest.fail(
            f"{section} restore mismatch in configurable fields: "
            f"{_mismatched_fields(final_view, expected)}"
        )


def _restore_global(router: NR2301Client, field: str, original: str) -> None:
    current = str(_config(router).get(field))
    if current != original:
        router.wifi.update_global_settings({field: original})
    assert str(_config(router).get(field)) == original


@pytest.mark.parametrize("target", ["0", "2"], ids=["power-0", "power-2"])
def test_power_level_candidate_and_restore(target: str) -> None:
    """Explore neighboring power_level candidates without imposing regional policy.

    `power_level` and diagnostic `wifi_power` are intentionally treated as
    separate fields. A passing case proves only that the top-level setter accepts
    and round-trips the candidate on this firmware; it does not assign a human
    meaning to the raw value and does not claim that the enum is exhaustive.
    """

    router = _client()
    try:
        original = str(_config(router)["power_level"])
        if target == original:
            pytest.skip(f"power_level is already {target}")
        try:
            actual = router.wifi.update_global_settings({"power_level": target})
            assert str(actual["config"].get("power_level")) == target
        finally:
            _restore_global(router, "power_level", original)
    finally:
        router.close()


def test_global_maxassoc_min_candidate_and_restore() -> None:
    router = _client()
    try:
        original = str(_config(router)["maxassoc"])
        target = "1"
        if original == target:
            pytest.skip("global maxassoc is already 1")
        try:
            actual = router.wifi.update_global_settings({"maxassoc": target})
            assert str(actual["config"].get("maxassoc")) == target
        finally:
            _restore_global(router, "maxassoc", original)
    finally:
        router.close()


def test_guest_maxassoc_min_and_restore() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_GUEST"])
        target = "1"
        if str(original.get("maxassoc")) == target:
            pytest.skip("Guest maxassoc is already 1")
        try:
            actual = router.wifi.update_ap_section("wifi_if_GUEST", {"maxassoc": target})
            assert str(actual.get("maxassoc")) == target
        finally:
            _restore_section(router, "wifi_if_GUEST", original)
    finally:
        router.close()


def test_guest_band_mode_toggle_and_restore() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_GUEST"])
        current = str(original.get("band_mode"))
        assert current in {"2.4G", "5G"}
        target = "5G" if current == "2.4G" else "2.4G"
        try:
            actual = router.wifi.update_ap_section("wifi_if_GUEST", {"band_mode": target})
            assert str(actual.get("band_mode")) == target
        finally:
            _restore_section(router, "wifi_if_GUEST", original)
    finally:
        router.close()


@pytest.mark.parametrize(
    ("section", "synthetic_ssid"),
    [
        ("wifi_if_24G", "NR2301-SDK-24G"),
        ("wifi_if_5G", "NR2301-SDK-5G"),
        ("wifi_if_DUAL", "NR2301-SDK-DUAL"),
        ("wifi_if_GUEST", "NR2301-SDK-GUEST"),
    ],
    ids=["24g", "5g", "dual", "guest"],
)
def test_synthetic_ssid_change_and_restore(section: str, synthetic_ssid: str) -> None:
    """Verify SSID mutability without printing the real/original SSID."""

    router = _client()
    try:
        original = copy.deepcopy(_config(router)[section])
        assert isinstance(original.get("ssid"), str)
        if original["ssid"] == synthetic_ssid:
            pytest.skip("synthetic SSID unexpectedly equals current SSID")
        try:
            actual = router.wifi.update_ap_section(section, {"ssid": synthetic_ssid})
            assert actual.get("ssid") == synthetic_ssid
        finally:
            _restore_section(router, section, original)
    finally:
        router.close()


def test_24g_runtime_advertised_upper_channel_and_restore() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_24G"])
        target = str(original["last_channel"])
        assert int(str(original["first_channel"])) <= int(target)
        if str(original.get("channel")) == target:
            pytest.skip("2.4-GHz configured channel is already the advertised upper bound")
        try:
            actual = router.wifi.update_ap_section("wifi_if_24G", {"channel": target})
            assert str(actual.get("channel")) == target
        finally:
            _restore_section(router, "wifi_if_24G", original)
    finally:
        router.close()


@pytest.mark.parametrize(
    ("category", "target"),
    [
        ("indoor_or_dfs", "52"),
        ("dfs", "100"),
        ("dfs", "140"),
    ],
    ids=["52-indoor-or-dfs", "100-dfs", "140-dfs-upper"],
)
def test_5g_runtime_advertised_channel_category_and_restore(category: str, target: str) -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_5G"])
        channel_list = original.get("channel_list")
        assert isinstance(channel_list, dict)
        advertised = str(channel_list.get(category, "")).split()
        if target not in advertised:
            pytest.skip(f"router does not advertise {target} in {category}")
        if str(original.get("channel")) == target:
            pytest.skip(f"5-GHz configured channel is already {target}")
        try:
            # Configured-channel read-back is the contract check. DFS/CAC may
            # delay the actual operating channel and is intentionally not
            # conflated with setter persistence.
            actual = router.wifi.update_ap_section("wifi_if_5G", {"channel": target})
            assert str(actual.get("channel")) == target
        finally:
            _restore_section(router, "wifi_if_5G", original)
    finally:
        router.close()


_WEBUI_ENUM_CASES = [
    ("wifi_if_24G", "net_mode", ("11b", "11bg", "11bgn", "11bgnax")),
    ("wifi_if_5G", "net_mode", ("11a", "11an", "11anac", "11anacax")),
    ("wifi_if_24G", "bandwidth", ("HT20/HT40", "HT20", "HT40")),
    ("wifi_if_5G", "bandwidth", ("HT20/HT40/HT80", "HT20", "HT40", "HT80")),
]


@pytest.mark.parametrize(
    ("section", "field", "options"),
    _WEBUI_ENUM_CASES,
    ids=["24g-net-mode-all", "5g-net-mode-all", "24g-bandwidth-all", "5g-bandwidth-all"],
)
def test_all_original_webui_radio_enum_values_and_restore(
    section: str, field: str, options: tuple[str, ...]
) -> None:
    """Exercise every original WebUI option token, not only one alternate."""

    router = _client()
    try:
        original = copy.deepcopy(_config(router)[section])
        original_value = str(original[field])
        assert original_value in options
        try:
            for target in options:
                if target == original_value:
                    continue
                actual = router.wifi.update_ap_section(section, {field: target})
                assert str(actual.get(field)) == target, f"{section}.{field} did not persist {target!r}"
        finally:
            _restore_section(router, section, original)
    finally:
        router.close()


def test_authenticated_wifi_scan_without_exposing_scan_results() -> None:
    """Confirm normal-admin scan access without printing nearby SSIDs/BSSIDs."""

    router = _client()
    try:
        response = router.wifi.scan()
        assert isinstance(response, Mapping)
        # Do not assert or print scan-list contents: they may contain nearby
        # network identifiers. Successful structured return is sufficient for
        # the authentication/SDK transport check.
    finally:
        router.close()
