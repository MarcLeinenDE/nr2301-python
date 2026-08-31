# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import os

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


def _restore_section(router: NR2301Client, section: str, original: dict) -> None:
    current = _config(router).get(section)
    if current != original:
        router.wifi.update_ap_section(section, original)
    assert _config(router).get(section) == original


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


@pytest.mark.parametrize("section", ["wifi_if_24G", "wifi_if_5G"])
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
            router.call(
                "wireless",
                "wifi_set_ap_config",
                data={"maxassoc": target},
                timeout=30.0,
            )
            assert str(_config(router).get("maxassoc")) == target
        finally:
            if str(_config(router).get("maxassoc")) != original:
                router.call(
                    "wireless",
                    "wifi_set_ap_config",
                    data={"maxassoc": original},
                    timeout=30.0,
                )
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
            # A short, valid-looking schedule that should not overlap the
            # current local time for long. We test persistence, not timer fire.
            target.update({
                "start_hour": 3,
                "start_minute": 17,
                "end_hour": 3,
                "end_minute": 19,
            })
        try:
            actual = router.wifi.update_ap_section("wifi_timed_off", target)
            for key, value in target.items():
                assert actual.get(key) == value
        finally:
            _restore_section(router, "wifi_timed_off", original)
    finally:
        router.close()
