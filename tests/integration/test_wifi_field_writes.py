# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical Wi-Fi write tests require NR2301_WRITE_INTEGRATION=1",
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




_WEBUI_ENUM_CASES = [
    ("wifi_if_24G", "net_mode", ("11b", "11bg", "11bgn", "11bgnax")),
    ("wifi_if_5G", "net_mode", ("11a", "11an", "11anac", "11anacax")),
    ("wifi_if_24G", "bandwidth", ("HT20/HT40", "HT20", "HT40")),
    ("wifi_if_5G", "bandwidth", ("HT20/HT40/HT80", "HT20", "HT40", "HT80")),
]


def _adjacent_alternate(current: str, options: tuple[str, ...]) -> str:
    assert current in options, f"router returned {current!r}, not in the original WebUI option contract"
    index = options.index(current)
    if index > 0:
        return options[index - 1]
    return options[1]


def _choose_24g_channel(block: dict) -> str:
    first = int(str(block["first_channel"]))
    last = int(str(block["last_channel"]))
    current_configured = str(block["channel"])
    current_live = str(block.get("cur_channel", ""))
    for channel in range(first, last + 1):
        candidate = str(channel)
        if candidate not in {current_configured, current_live}:
            return candidate
    pytest.skip("no alternate 2.4-GHz channel is available")


def _choose_5g_channel(block: dict) -> str:
    listed = block.get("channel_list")
    if not isinstance(listed, dict):
        pytest.skip("router did not expose a 5-GHz channel_list")
    candidates: list[str] = []
    # Prefer non-DFS indoor channels to avoid unnecessary DFS/CAC delays.
    for key in ("indoor", "indoor_or_dfs", "dfs"):
        raw = listed.get(key)
        if isinstance(raw, str):
            candidates.extend(raw.split())
    current_configured = str(block["channel"])
    current_live = str(block.get("cur_channel", ""))
    for candidate in candidates:
        if candidate not in {current_configured, current_live}:
            return candidate
    pytest.skip("no alternate 5-GHz channel is available")


def test_24g_channel_fixed_and_restore_auto() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_24G"])
        target = _choose_24g_channel(original)
        try:
            actual = router.wifi.update_ap_section("wifi_if_24G", {"channel": target})
            assert str(actual.get("channel")) == target
        finally:
            _restore_section(router, "wifi_if_24G", original)
    finally:
        router.close()


def test_5g_channel_fixed_and_restore_auto() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_if_5G"])
        target = _choose_5g_channel(original)
        try:
            actual = router.wifi.update_ap_section("wifi_if_5G", {"channel": target})
            assert str(actual.get("channel")) == target
        finally:
            _restore_section(router, "wifi_if_5G", original)
    finally:
        router.close()


@pytest.mark.parametrize("section", ["wifi_if_24G", "wifi_if_5G", "wifi_if_DUAL", "wifi_if_GUEST"])
def test_hidden_toggle_and_restore(section: str) -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)[section])
        current = str(original["hidden"])
        assert current in {"0", "1"}
        target = "1" if current == "0" else "0"
        try:
            actual = router.wifi.update_ap_section(section, {"hidden": target})
            assert str(actual.get("hidden")) == target
        finally:
            _restore_section(router, section, original)
    finally:
        router.close()


@pytest.mark.parametrize("section", ["wifi_if_24G", "wifi_if_5G"])
def test_isolation_toggle_and_restore(section: str) -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)[section])
        current = str(original["isolate"])
        assert current in {"0", "1"}
        target = "1" if current == "0" else "0"
        try:
            actual = router.wifi.update_ap_section(section, {"isolate": target})
            assert str(actual.get("isolate")) == target
        finally:
            _restore_section(router, section, original)
    finally:
        router.close()


def test_global_maxassoc_31_and_restore() -> None:
    router = _client()
    try:
        before = _config(router)
        original = str(before["maxassoc"])
        if original == "31":
            target = "30"
        else:
            target = "31"
        # This is an explicit exploratory write. The physical test router is
        # non-production and the exact accepted global range is part of the
        # contract being established. Never generalize the accepted value into
        # a range until the physical result is normalized upstream.
        try:
            actual = router.wifi.update_global_settings({"maxassoc": target})
            assert str(actual["config"].get("maxassoc")) == target
        finally:
            if str(_config(router).get("maxassoc")) != original:
                router.wifi.update_global_settings({"maxassoc": original})
            assert str(_config(router).get("maxassoc")) == original
    finally:
        router.close()


def test_timed_off_block_enable_and_restore() -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)["wifi_timed_off"])
        target = copy.deepcopy(original)
        current_enable = int(target.get("enable", 0))
        target["enable"] = 0 if current_enable else 1
        if target["enable"] == 1:
            # Place the test window six hours ahead of the PC clock so the
            # schedule is not expected to fire during this short persistence test.
            start = datetime.now() + timedelta(hours=6)
            end = start + timedelta(minutes=2)
            target.update({
                "start_hour": start.hour,
                "start_minute": start.minute,
                "end_hour": end.hour,
                "end_minute": end.minute,
            })
        try:
            actual = router.wifi.update_ap_section("wifi_timed_off", target)
            for key, value in target.items():
                assert actual.get(key) == value
        finally:
            _restore_section(router, "wifi_timed_off", original)
    finally:
        router.close()


def test_master_switch_off_and_restore() -> None:
    router = _client()
    try:
        original = str(_config(router)["switch"])
        assert original in {"on", "off"}
        target = "off" if original == "on" else "on"
        try:
            actual = router.wifi.update_global_settings({"switch": target})
            assert str(actual["config"].get("switch")) == target
        finally:
            if str(_config(router).get("switch")) != original:
                router.wifi.update_global_settings({"switch": original})
            assert str(_config(router).get("switch")) == original
    finally:
        router.close()

@pytest.mark.parametrize(
    ("section", "field", "options"),
    _WEBUI_ENUM_CASES,
    ids=["24g-net-mode", "5g-net-mode", "24g-bandwidth", "5g-bandwidth"],
)
def test_original_webui_radio_enum_change_and_restore(
    section: str, field: str, options: tuple[str, ...]
) -> None:
    router = _client()
    try:
        original = copy.deepcopy(_config(router)[section])
        current = str(original[field])
        target = _adjacent_alternate(current, options)
        try:
            actual = router.wifi.update_ap_section(section, {field: target})
            assert str(actual.get(field)) == target
        finally:
            _restore_section(router, section, original)
    finally:
        router.close()

