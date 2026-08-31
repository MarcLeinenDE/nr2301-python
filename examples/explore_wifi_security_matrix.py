# SPDX-License-Identifier: GPL-3.0-or-later
"""Explore the source-verified NR2301 Wi-Fi encryption token matrix safely.

This is a deliberately opt-in physical-router research tool. It uses only
synthetic test keys, never prints or stores the router's real SSIDs/keys, and
restores each AP block before moving to the next case.

The goal is classification, not a green test suite: ACCEPTED, COERCED and
REJECTED/UNVERIFIED outcomes are all useful protocol evidence.
"""

from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nr2301 import NR2301Client


TOKENS = (
    "psk-mixed+ccmp",
    "sae-mixed",
    "sae",
    "psk2+ccmp",
    "psk+ccmp",
    "psk2+tkip+ccmp",
    "psk+tkip+ccmp",
    "psk-mixed+tkip+ccmp",
    "psk2+tkip",
    "psk+tkip",
    "psk-mixed+tkip",
    "wep-mixed",
    "none",
)

SECTIONS = (
    "wifi_if_24G",
    "wifi_if_5G",
    "wifi_if_DUAL",
    "wifi_if_GUEST",
)

# Synthetic values only. These strings are intentionally safe to publish.
PSK_TEST_KEY = "NR2301-TestKey-2026"
WEP_TEST_KEY = "NR2301WEPKEYX"  # 13 ASCII characters


def _client() -> NR2301Client:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise SystemExit(
            "Refusing physical writes: set NR2301_WRITE_INTEGRATION=1 explicitly."
        )
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise SystemExit("NR2301_PASSWORD is required but was not found in the environment.")
    router = NR2301Client(
        os.environ.get("NR2301_URL", "http://zyxel.home"),
        username=os.environ.get("NR2301_USERNAME", "admin"),
        password=password,
    )
    router.login()
    return router


def _config(router: NR2301Client) -> dict[str, Any]:
    response = router.wifi.config()
    config = response.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("wifi_get_ap_config returned no config mapping")
    return config


def _password_modified(config: dict[str, Any]) -> int | str | None:
    value = config.get("password_modified")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit() and len(value) <= 8:
        return value
    return None


def _test_key(token: str) -> str:
    if token == "none":
        return ""
    if token == "wep-mixed":
        return WEP_TEST_KEY
    return PSK_TEST_KEY


def _mismatched_fields(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    return sorted(
        key
        for key in set(actual) | set(expected)
        if actual.get(key) != expected.get(key)
    )


def _restore_section(
    router: NR2301Client,
    section: str,
    original: dict[str, Any],
) -> dict[str, Any]:
    """Restore one block and report only mismatching field names on failure."""

    current = _config(router).get(section)
    if not isinstance(current, dict):
        raise RuntimeError(f"restore failed: {section} is not a mapping")

    restore_error_type: str | None = None
    if current != original:
        try:
            router.wifi.update_ap_section(
                section,
                original,
                write_timeout=45.0,
                recovery_attempts=20,
                recovery_delay=1.0,
                recovery_timeout=3.0,
            )
        except Exception as exc:  # classification happens after final read-back
            restore_error_type = type(exc).__name__

    final = _config(router).get(section)
    if not isinstance(final, dict):
        raise RuntimeError(f"restore failed: {section} final state is not a mapping")
    if final != original:
        fields = _mismatched_fields(final, original)
        suffix = f"; setter_error={restore_error_type}" if restore_error_type else ""
        raise RuntimeError(
            f"restore verification failed for {section}; mismatching fields={fields}{suffix}"
        )
    return _config(router)


def _classify(
    requested_token: str,
    requested_key: str,
    actual_block: dict[str, Any] | None,
    setter_error_type: str | None,
) -> tuple[str, str | None, bool | None]:
    if not isinstance(actual_block, dict):
        return "UNVERIFIED", None, None

    raw_token = actual_block.get("encryption")
    readback_token = str(raw_token) if raw_token is not None else None
    key_match = actual_block.get("key") == requested_key

    if readback_token != requested_token:
        return "COERCED", readback_token, key_match
    if requested_token == "none" and not key_match:
        # Open mode may intentionally retain or ignore the stored key while the
        # encryption mode itself is accepted. Preserve that distinction.
        return "ACCEPTED_TOKEN_KEY_IGNORED", readback_token, key_match
    if key_match:
        return "ACCEPTED", readback_token, True
    if setter_error_type:
        return "TOKEN_ACCEPTED_KEY_DIFFERENT", readback_token, False
    return "TOKEN_ACCEPTED_KEY_DIFFERENT", readback_token, False


def _print_row(row: dict[str, Any]) -> None:
    key_state = row.get("key_match")
    if key_state is True:
        key_text = "yes"
    elif key_state is False:
        key_text = "no"
    else:
        key_text = "n/a"
    print(
        f"{row['section']:<14} {row['requested_token']:<23} "
        f"{row['classification']:<28} "
        f"readback={row.get('readback_token') or '<none>':<23} "
        f"key_match={key_text:<3} "
        f"password_modified={row.get('password_modified_before')}"
        f"->{row.get('password_modified_after_write')}"
        f"->{row.get('password_modified_after_restore')}"
    )


def main() -> int:
    print("NR2301 sanitized Wi-Fi security matrix exploration")
    print("Physical writes: YES (hard opt-in). USB/management mode is NOT touched.")
    print("Real SSIDs, Wi-Fi keys and router password are never printed or stored.")
    print("Each case is restored before the next case.\n")

    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    router = _client()
    try:
        initial = _config(router)
        initial_password_modified = _password_modified(initial)

        for section in SECTIONS:
            current_section = initial.get(section)
            if not isinstance(current_section, dict):
                print(f"{section}: skipped because the router did not return a mapping")
                continue

            for token in TOKENS:
                before_config = _config(router)
                original = before_config.get(section)
                if not isinstance(original, dict):
                    raise RuntimeError(f"{section} disappeared before {token}")
                original = copy.deepcopy(original)
                pwd_before = _password_modified(before_config)
                synthetic_key = _test_key(token)
                setter_error_type: str | None = None
                actual_block: dict[str, Any] | None = None
                pwd_after_write: int | str | None = None

                try:
                    try:
                        router.wifi.update_ap_section(
                            section,
                            {"encryption": token, "key": synthetic_key},
                            write_timeout=45.0,
                            recovery_attempts=8,
                            recovery_delay=1.0,
                            recovery_timeout=3.0,
                        )
                    except Exception as exc:
                        # Never print exception text: it could contain context
                        # that is unnecessary for the sanitized research report.
                        setter_error_type = type(exc).__name__

                    try:
                        after_write = _config(router)
                        block = after_write.get(section)
                        actual_block = block if isinstance(block, dict) else None
                        pwd_after_write = _password_modified(after_write)
                    except Exception as exc:
                        if setter_error_type is None:
                            setter_error_type = type(exc).__name__

                    classification, readback_token, key_match = _classify(
                        token,
                        synthetic_key,
                        actual_block,
                        setter_error_type,
                    )
                finally:
                    after_restore = _restore_section(router, section, original)

                row = {
                    "section": section,
                    "requested_token": token,
                    "classification": classification,
                    "readback_token": readback_token,
                    "key_match": key_match,
                    "setter_error_type": setter_error_type,
                    "password_modified_before": pwd_before,
                    "password_modified_after_write": pwd_after_write,
                    "password_modified_after_restore": _password_modified(after_restore),
                }
                rows.append(row)
                _print_row(row)

        final = _config(router)
        final_password_modified = _password_modified(final)
    finally:
        router.close()

    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["classification"])
        counts[key] = counts.get(key, 0) + 1

    report = {
        "schema": "nr2301.sanitized_wifi_security_matrix",
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_token_count": len(TOKENS),
        "section_count": len(SECTIONS),
        "rows": rows,
        "classification_counts": counts,
        "password_modified_initial": initial_password_modified,
        "password_modified_final": final_password_modified,
        "duration_seconds": round(time.monotonic() - started, 3),
        "privacy": "No real SSID, Wi-Fi key, router password, session cookie, MAC or scan result is stored.",
    }

    report_path = Path(
        os.environ.get("NR2301_REPORT_PATH", "nr2301_wifi_security_matrix_report.json")
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\nClassification counts:")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    print(
        "password_modified campaign: "
        f"{initial_password_modified} -> {final_password_modified}"
    )
    print(f"Sanitized report: {report_path}")
    print("Upload that JSON report for API normalization; it contains no real Wi-Fi credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
