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


def _find_by_mac(rows: list[Mapping[str, object]], mac: str) -> Mapping[str, object] | None:
    target = mac.lower()
    for row in rows:
        value = row.get("mac")
        if isinstance(value, str) and value.lower() == target:
            return row
    return None


def _require_black_mode(router: NR2301Client) -> None:
    mode = router.statistics.filter_mode().get("mode")
    print(f"STAT_WRITE_PREFLIGHT filter_mode={mode}")
    if mode != "black":
        pytest.skip("reversible statistics write test currently requires Black filter mode")


def test_inactive_client_alias_change_and_restore() -> None:
    router = _client()
    original_alias: str | None = None
    target_mac: str | None = None
    changed = False
    try:
        _require_black_mode(router)
        initial_rows = _rows(router.statistics.inactive_clients())
        print(f"STAT_ALIAS_STATE initial_inactive_count={len(initial_rows)}")
        if not initial_rows:
            pytest.skip("no inactive client exists for reversible alias test")

        target = initial_rows[0]
        mac_value = target.get("mac")
        alias_value = target.get("alias", "")
        if not isinstance(mac_value, str) or not mac_value.strip():
            pytest.skip("selected inactive row has no usable MAC")
        if not isinstance(alias_value, str):
            pytest.skip("selected inactive row alias is not a string")

        target_mac = mac_value
        original_alias = alias_value
        test_alias = "nr2301-sdk-test"
        if original_alias == test_alias:
            test_alias = "nr2301-sdk-test-2"

        response = router.statistics.set_alias(target_mac, test_alias)
        print(f"STAT_ALIAS_ACTION set_test_alias response_keys={','.join(sorted(response.keys())) or '-'}")
        changed = True

        changed_row = _find_by_mac(_rows(router.statistics.inactive_clients()), target_mac)
        if changed_row is None:
            pytest.fail("alias target disappeared from inactive view after set_alias")
        if changed_row.get("alias") != test_alias:
            pytest.fail("set_alias read-back did not match the synthetic alias")
        print("STAT_ALIAS_STATE synthetic_alias_readback=OK")

    finally:
        if changed and target_mac is not None and original_alias is not None:
            router.statistics.set_alias(target_mac, original_alias)
            restored_row = _find_by_mac(_rows(router.statistics.inactive_clients()), target_mac)
            if restored_row is None:
                pytest.fail("alias target disappeared during restore verification")
            if restored_row.get("alias") != original_alias:
                pytest.fail("original alias was not restored")
            print("STAT_ALIAS_CLEANUP original_alias_restored=OK")
        router.close()


def test_synthetic_forbidden_add_and_remove() -> None:
    router = _client()
    candidate: str | None = None
    added = False
    try:
        _require_black_mode(router)
        responses = [
            router.statistics.active_clients(),
            router.statistics.inactive_clients(),
            router.statistics.allow_clients(),
            router.statistics.forbidden_clients(),
        ]
        existing: set[str] = set()
        for response in responses:
            for row in _rows(response):
                value = row.get("mac")
                if isinstance(value, str):
                    existing.add(value.lower())

        candidates = [
            "02:FA:CE:00:00:01",
            "02:FA:CE:00:00:02",
            "02:FA:CE:00:00:03",
            "02:FA:CE:00:00:04",
        ]
        candidate = next((value for value in candidates if value.lower() not in existing), None)
        if candidate is None:
            pytest.skip("all synthetic MAC candidates unexpectedly exist")

        response = router.statistics.set_forbidden(
            candidate,
            True,
            alias="nr2301-sdk-test",
        )
        print(f"STAT_FORBIDDEN_ACTION add result={response.get('result')}")
        added = True

        row = _find_by_mac(_rows(router.statistics.forbidden_clients()), candidate)
        if row is None:
            pytest.fail("synthetic MAC did not appear in forbidden view")
        if "forbidden" in row and row.get("forbidden") != 1:
            pytest.fail("synthetic forbidden row did not read back forbidden=1")
        print("STAT_FORBIDDEN_STATE add_readback=OK")

    finally:
        if added and candidate is not None:
            response = router.statistics.set_forbidden(candidate, False)
            print(f"STAT_FORBIDDEN_ACTION remove result={response.get('result')}")
            if _find_by_mac(_rows(router.statistics.forbidden_clients()), candidate) is not None:
                pytest.fail("synthetic forbidden row remained after cleanup")
            print("STAT_FORBIDDEN_CLEANUP removed=OK")
        router.close()
