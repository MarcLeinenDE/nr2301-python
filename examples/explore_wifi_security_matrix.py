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

# Runtime/capability metadata returned inside AP blocks but not part of the
# mutable configuration contract. In particular, `cur_channel` can legitimately
# change after restoring configured `channel=0` (auto channel selection).
_NON_CONFIG_FIELDS: dict[str, set[str]] = {
    "wifi_if_24G": {"cur_channel", "first_channel", "last_channel"},
    "wifi_if_5G": {"cur_channel", "channel_list"},
}

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


def _configurable_view(section: str, block: dict[str, Any]) -> dict[str, Any]:
    ignored = _NON_CONFIG_FIELDS.get(section, set())
    return {key: value for key, value in block.items() if key not in ignored}


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
    """Restore mutable fields and ignore runtime/capability metadata."""

    expected = _configurable_view(section, original)
    current = _config(router).get(section)
    if not isinstance(current, dict):
        raise RuntimeError(f"restore failed: {section} is not a mapping")

    restore_error_type: str | None = None
    if _configurable_view(section, current) != expected:
        try:
            router.wifi.update_ap_section(
                section,
                expected,
                write_timeout=45.0,
                recovery_attempts=20,
                recovery_delay=1.0,
                recovery_timeout=3.0,
            )
        except Exception as exc:  # final read-back decides whether restore worked
            restore_error_type = type(exc).__name__

    final_config = _config(router)
    final = final_config.get(section)
    if not isinstance(final, dict):
        raise RuntimeError(f"restore failed: {section} final state is not a mapping")

    final_view = _configurable_view(section, final)
    if final_view != expected:
        fields = _mismatched_fields(final_view, expected)
        suffix = f"; setter_error={restore_error_type}" if restore_error_type else ""
        raise RuntimeError(
            f"restore verification failed for {section}; mismatching configurable fields={fields}{suffix}"
        )
    return final_config


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


def _parse_start() -> tuple[str, str] | None:
    raw = os.environ.get("NR2301_SECURITY_START", "").strip()
    if not raw:
        return None
    try:
        section, token = raw.split(":", 1)
    except ValueError as exc:
        raise SystemExit(
            "NR2301_SECURITY_START must be SECTION:TOKEN, for example "
            "wifi_if_5G:psk+tkip+ccmp"
        ) from exc
    if section not in SECTIONS or token not in TOKENS:
        raise SystemExit(
            f"invalid NR2301_SECURITY_START={raw!r}; use a known section and token"
        )
    return section, token


def _ordered_cases(start: tuple[str, str] | None) -> list[tuple[str, str]]:
    cases = [(section, token) for section in SECTIONS for token in TOKENS]
    if start is None:
        return cases
    try:
        index = cases.index(start)
    except ValueError as exc:
        raise SystemExit(f"start case {start!r} is not in the matrix") from exc
    return cases[index:]


def _build_report(
    *,
    rows: list[dict[str, Any]],
    initial_password_modified: int | str | None,
    final_password_modified: int | str | None,
    started: float,
    start: tuple[str, str] | None,
    complete: bool,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["classification"])
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema": "nr2301.sanitized_wifi_security_matrix",
        "schema_version": 2,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_token_count": len(TOKENS),
        "section_count": len(SECTIONS),
        "start_at": None if start is None else f"{start[0]}:{start[1]}",
        "complete_requested_range": complete,
        "rows": rows,
        "classification_counts": counts,
        "password_modified_initial": initial_password_modified,
        "password_modified_final": final_password_modified,
        "duration_seconds": round(time.monotonic() - started, 3),
        "restore_policy": (
            "Exact mutable-config restore. Runtime/capability metadata such as cur_channel, "
            "first_channel, last_channel and channel_list is not treated as restorable state."
        ),
        "privacy": "No real SSID, Wi-Fi key, router password, session cookie, MAC or scan result is stored.",
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    print("NR2301 sanitized Wi-Fi security matrix exploration")
    print("Physical writes: YES (hard opt-in). USB/management mode is NOT touched.")
    print("Real SSIDs, Wi-Fi keys and router password are never printed or stored.")
    print("Each case is restored before the next case.")
    print("Runtime cur_channel changes are not treated as configuration-restore failures.\n")

    started = time.monotonic()
    start = _parse_start()
    cases = _ordered_cases(start)
    if start is not None:
        print(f"Resuming matrix at: {start[0]} / {start[1]}\n")

    report_path = Path(
        os.environ.get("NR2301_REPORT_PATH", "nr2301_wifi_security_matrix_report.json")
    )
    rows: list[dict[str, Any]] = []
    initial_password_modified: int | str | None = None
    final_password_modified: int | str | None = None
    complete = False

    router = _client()
    try:
        initial = _config(router)
        initial_password_modified = _password_modified(initial)

        for section, token in cases:
            current_section = initial.get(section)
            if not isinstance(current_section, dict):
                print(f"{section}: skipped because the router did not return a mapping")
                continue

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
                    # Never print exception text: it could contain unnecessary
                    # request/read-back context. The type is enough for evidence.
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

            # Checkpoint after every successfully restored case so a later
            # interruption does not discard the completed research range.
            final_password_modified = _password_modified(after_restore)
            _write_report(
                report_path,
                _build_report(
                    rows=rows,
                    initial_password_modified=initial_password_modified,
                    final_password_modified=final_password_modified,
                    started=started,
                    start=start,
                    complete=False,
                ),
            )

        final = _config(router)
        final_password_modified = _password_modified(final)
        complete = True
    finally:
        router.close()
        # Preserve completed checkpoint rows even if a later case aborts.
        _write_report(
            report_path,
            _build_report(
                rows=rows,
                initial_password_modified=initial_password_modified,
                final_password_modified=final_password_modified,
                started=started,
                start=start,
                complete=complete,
            ),
        )

    report = _build_report(
        rows=rows,
        initial_password_modified=initial_password_modified,
        final_password_modified=final_password_modified,
        started=started,
        start=start,
        complete=complete,
    )

    print("\nClassification counts:")
    for key in sorted(report["classification_counts"]):
        print(f"  {key}: {report['classification_counts'][key]}")
    print(
        "password_modified campaign: "
        f"{initial_password_modified} -> {final_password_modified}"
    )
    print(f"Sanitized report: {report_path}")
    print("Upload that JSON report for API normalization; it contains no real Wi-Fi credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
