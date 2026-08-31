# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
import os

import pytest

from nr2301 import NR2301Client

pytestmark = pytest.mark.integration

if os.environ.get("NR2301_INTEGRATION") != "1":
    pytest.skip(
        "physical statistics client-view test requires NR2301_INTEGRATION=1",
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


def _sanitized_summary(label: str, response: Mapping[str, object]) -> None:
    clients = response.get("clients_info", [])
    assert isinstance(clients, list)
    field_names: set[str] = set()
    for item in clients:
        assert isinstance(item, Mapping)
        field_names.update(str(key) for key in item.keys())

    # Deliberately report only counts/schema keys. Never print client MAC/IP/name/alias.
    print(
        f"STAT_CLIENT_VIEW view={label} count={len(clients)} "
        f"fields={','.join(sorted(field_names)) if field_names else '-'}"
    )


def test_statistics_explicit_client_views() -> None:
    router = _client()
    try:
        mode = router.statistics.filter_mode()
        print(f"STAT_CLIENT_FILTER mode={mode.get('mode')} result={mode.get('result')}")

        views = [
            ("active", router.statistics.active_clients),
            ("inactive", router.statistics.inactive_clients),
            ("allow", router.statistics.allow_clients),
            ("forbidden", router.statistics.forbidden_clients),
        ]
        for label, helper in views:
            response = helper()
            _sanitized_summary(label, response)
    finally:
        router.close()
