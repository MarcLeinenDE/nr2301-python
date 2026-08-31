# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
    pytest.skip(
        "physical statistics write tests require NR2301_WRITE_INTEGRATION=1",
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
        timeout=5.0,
    )
    router.login()
    return router


def _rows(response: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = response.get("clients_info", [])
    if not isinstance(value, list):
        pytest.fail("clients_info is not a list")
    rows: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            pytest.fail("clients_info contains a non-object row")
        rows.append(item)
    return rows


def _find(rows: list[Mapping[str, object]], mac: str) -> Mapping[str, object] | None:
    target = mac.lower()
    for row in rows:
        value = row.get("mac")
        if isinstance(value, str) and value.lower() == target:
            return row
    return None


def _all_rows(router: NR2301Client) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for response in (
        router.statistics.active_clients(),
        router.statistics.inactive_clients(),
        router.statistics.allow_clients(),
        router.statistics.forbidden_clients(),
    ):
        rows.extend(_rows(response))
    return rows


def _candidate(router: NR2301Client) -> str:
    existing = {
        str(row.get("mac")).lower()
        for row in _all_rows(router)
        if isinstance(row.get("mac"), str)
    }
    candidates = [
        "02:FA:CE:10:00:01",
        "02:FA:CE:10:00:02",
        "02:FA:CE:10:00:03",
        "02:FA:CE:10:00:04",
    ]
    value = next((item for item in candidates if item.lower() not in existing), None)
    if value is None:
        pytest.skip("all synthetic MAC candidates unexpectedly exist")
    return value


def test_synthetic_allow_then_clear_offline_history() -> None:
    router = _client()
    candidate: str | None = None
    created = False
    try:
        mode = router.statistics.filter_mode().get("mode")
        print(f"STAT_ALLOW_PREFLIGHT filter_mode={mode}")
        if mode != "black":
            pytest.skip("synthetic allow/clear test requires Black filter mode")

        candidate = _candidate(router)
        response = router.statistics.set_allow(
            candidate,
            True,
            alias="nr2301-sdk-allow-test",
        )
        print(f"STAT_ALLOW_ACTION enable result={response.get('result')}")
        created = True

        inactive = _rows(router.statistics.inactive_clients())
        row = _find(inactive, candidate)
        if row is None:
            pytest.fail("synthetic set_allow row did not appear in inactive view in Black mode")
        if "forbidden" in row and row.get("forbidden") != 0:
            pytest.fail("synthetic set_allow row did not read back forbidden=0")
        if _find(_rows(router.statistics.allow_clients()), candidate) is not None:
            pytest.fail("Black-mode synthetic set_allow unexpectedly appeared in allow view")
        print("STAT_ALLOW_STATE inactive_readback=OK allow_view_absent=OK")

        cleared = router.statistics.clear_offline_user(candidate)
        print(f"STAT_CLEAR_ACTION clear_offline_user result={cleared.get('result')}")

        if _find(_all_rows(router), candidate) is not None:
            pytest.fail("synthetic client remained in an explicit client view after clear_offline_user")
        created = False
        print("STAT_CLEAR_CLEANUP synthetic_client_absent=OK")

    finally:
        if created and candidate is not None:
            # Cleanup is intentionally limited to the synthetic candidate.
            try:
                router.statistics.clear_offline_user(candidate)
            finally:
                # If firmware materialized a filter row instead of only history,
                # remove that synthetic filter state as well.
                if _find(_rows(router.statistics.forbidden_clients()), candidate) is not None:
                    router.statistics.set_forbidden(candidate, False)
                if _find(_rows(router.statistics.allow_clients()), candidate) is not None:
                    router.statistics.set_allow(candidate, False)
            print("STAT_CLEAR_CLEANUP fallback_attempted=YES")
        router.close()
