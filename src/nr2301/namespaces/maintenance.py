# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, TypedDict, cast

from ..exceptions import APIError, NR2301Error, ProtocolError, TransportError

if TYPE_CHECKING:
    from ..client import NR2301Client


_TIME_RE = re.compile(r"^([0-9]{1,2}):([0-9]{1,2})$")
_CONFIG_RESTORE_CHUNK_BYTES = 1024 * 1024
_CONFIG_RESTORE_MAX_BYTES = 200 * 1024 * 1024


class TimedRebootSettings(TypedDict, total=False):
    enable: int
    repeat: int
    result: int
    time: str


class MaintenanceRecoveryResult(TypedDict, total=False):
    """SDK-level recovery evidence for disruptive maintenance actions."""

    action_error: str
    action_response: dict[str, Any]
    boot_time_after: int
    boot_time_before: int
    chunk_count: int
    outage_observed: bool
    uploaded_bytes: int


class MaintenanceNamespace:
    """Evidence-backed router maintenance settings that are safe to read."""

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def timed_reboot(self, *, timeout: float | None = None) -> TimedRebootSettings:
        """Return the configured automatic reboot schedule.

        The raw firmware time string is preserved. ACIY.3 has been observed
        returning an unpadded value such as ``0:0``; callers must therefore
        not assume that getter values are always textual ``HH:MM``.
        """

        return cast(
            TimedRebootSettings,
            self._client.call(
                "router",
                "router_get_timed_reboot",
                timeout=timeout,
            ),
        )

    def backup_config(
        self,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Run the legacy configuration-backup action.

        This API method creates/returns router-side backup metadata; it does
        **not** download the current stock-UI backup file from `/file.cgi`.
        Backup responses/files can expose secrets and must not be logged or
        committed without explicit sanitization.
        """

        response = self._client.call(
            "router",
            "router_backup_config",
            timeout=timeout,
        )
        rc = response.get("rc")
        if isinstance(rc, bool):
            raise ProtocolError(
                "router/router_backup_config returned invalid boolean rc"
            )
        try:
            numeric_rc = int(rc)
        except (TypeError, ValueError) as exc:
            raise ProtocolError(
                "router/router_backup_config returned invalid rc"
            ) from exc
        if numeric_rc != 0:
            raise APIError(
                "router/router_backup_config did not report rc=0",
                method_id="router/router_backup_config",
                response={"rc": rc},
            )
        return response

    def download_config_backup(
        self,
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Download the current stock-WebUI configuration backup bytes.

        The returned blob is secret-bearing and may contain credentials. The
        SDK intentionally does not log, parse or persist it.
        """

        payload = self._client.transport.file_download(
            params={
                "Action": "Download",
                "file": "backup_config",
                "dl": "1",
            },
            timeout=timeout,
        )
        if not payload:
            raise ProtocolError("configuration backup download returned no data")
        return payload

    def restore_config_backup(
        self,
        backup: bytes | bytearray | memoryview,
        *,
        chunk_size: int = _CONFIG_RESTORE_CHUNK_BYTES,
        action_timeout: float = 20.0,
        recovery_attempts: int = 120,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
        initial_delay: float = 1.0,
    ) -> MaintenanceRecoveryResult:
        """Restore a trusted configuration backup through the stock file CGI.

        ACIY.3's frontend sends sequential raw `application/octet-stream`
        POSTs to `/file.cgi?Action=Upload&file=restore_config`, using 1 MiB
        chunks and no multipart wrapper or Content-Range header.

        Configuration data is secret-bearing. The SDK never includes backup
        bytes in diagnostics. A response containing `other error` is treated
        as failure. The final upload is considered successful only after
        management recovers and `boot_time` proves a new boot.
        """

        if not isinstance(backup, (bytes, bytearray, memoryview)):
            raise TypeError("backup must be bytes-like")
        payload = bytes(backup)
        if not payload:
            raise ValueError("backup must not be empty")
        if len(payload) > _CONFIG_RESTORE_MAX_BYTES:
            raise ValueError("backup exceeds the stock frontend 200 MiB limit")
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise TypeError("chunk_size must be an int")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")

        self._validate_recovery_args(
            action_timeout=action_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
            initial_delay=initial_delay,
        )
        before = self._read_boot_time(timeout=recovery_timeout)
        params = {"Action": "Upload", "file": "restore_config"}
        chunk_count = (len(payload) + chunk_size - 1) // chunk_size
        final_action_error: NR2301Error | None = None

        for index in range(chunk_count):
            start = index * chunk_size
            end = min(len(payload), start + chunk_size)
            chunk = payload[start:end]
            final_chunk = index + 1 == chunk_count
            try:
                response = self._client.transport.file_upload(
                    chunk,
                    params=params,
                    timeout=action_timeout,
                )
            except TransportError as exc:
                if not final_chunk:
                    raise APIError(
                        "configuration restore upload failed before final chunk",
                        method_id="file.cgi/restore_config",
                        response={
                            "chunk_index": index,
                            "chunk_count": chunk_count,
                            "uploaded_bytes_before_failure": start,
                            "error": type(exc).__name__,
                        },
                    ) from exc
                final_action_error = exc
                break

            if b"other error" in response.lower():
                raise APIError(
                    "configuration restore was rejected by file.cgi",
                    method_id="file.cgi/restore_config",
                    response={
                        "chunk_index": index,
                        "chunk_count": chunk_count,
                        "uploaded_bytes_before_failure": start,
                    },
                )

        started = time.monotonic()
        if initial_delay:
            time.sleep(initial_delay)

        last_boot: int | None = None
        last_error: NR2301Error | None = None
        outage_observed = final_action_error is not None

        for attempt in range(recovery_attempts):
            try:
                current = self._read_boot_time(timeout=recovery_timeout)
                last_boot = current
                elapsed = time.monotonic() - started
                if current < before or (
                    outage_observed
                    and current <= int(elapsed) + 10
                    and before <= int(elapsed) + 10
                ):
                    result: MaintenanceRecoveryResult = {
                        "boot_time_before": before,
                        "boot_time_after": current,
                        "outage_observed": outage_observed,
                        "uploaded_bytes": len(payload),
                        "chunk_count": chunk_count,
                    }
                    if final_action_error is not None:
                        result["action_error"] = type(final_action_error).__name__
                    return result
            except NR2301Error as exc:
                outage_observed = True
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "boot_time_before": before,
            "boot_time_after": last_boot,
            "outage_observed": outage_observed,
            "uploaded_bytes": len(payload),
            "chunk_count": chunk_count,
        }
        if final_action_error is not None:
            details["action_error"] = type(final_action_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "configuration restore could not be verified by recovery and boot_time reset",
            method_id="file.cgi/restore_config",
            response=details,
        )

    def restart_web_server(
        self,
        *,
        action_timeout: float = 10.0,
        recovery_attempts: int = 30,
        recovery_delay: float = 0.5,
        recovery_timeout: float = 3.0,
        initial_delay: float = 0.5,
    ) -> MaintenanceRecoveryResult:
        """Restart only the management web server and verify recovery.

        ACIY.3 was physically observed returning HTTP 200 with an empty body,
        which the strict low-level JSON transport surfaces as `ProtocolError`.
        That is treated as inconclusive action-response loss; management
        recovery and a non-resetting router `boot_time` decide success.
        """

        self._validate_recovery_args(
            action_timeout=action_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
            initial_delay=initial_delay,
        )
        before = self._read_boot_time(timeout=recovery_timeout)

        action_response: dict[str, Any] | None = None
        action_error: NR2301Error | None = None
        try:
            action_response = self._client.call(
                "router",
                "restart_web_server",
                timeout=action_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            action_error = exc

        if initial_delay:
            time.sleep(initial_delay)

        after, outage_observed = self._recover_boot_time(
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
        )
        if after < before:
            raise APIError(
                "restart_web_server recovered after a full router reboot",
                method_id="router/restart_web_server",
                response={
                    "boot_time_before": before,
                    "boot_time_after": after,
                    "outage_observed": outage_observed,
                    "action_error": (
                        type(action_error).__name__
                        if action_error is not None
                        else None
                    ),
                },
            )

        result: MaintenanceRecoveryResult = {
            "boot_time_before": before,
            "boot_time_after": after,
            "outage_observed": outage_observed,
        }
        if action_response is not None:
            result["action_response"] = action_response
        if action_error is not None:
            result["action_error"] = type(action_error).__name__
        return result

    def reboot(
        self,
        *,
        action_timeout: float = 5.0,
        recovery_attempts: int = 90,
        recovery_delay: float = 1.0,
        recovery_timeout: float = 3.0,
        initial_delay: float = 1.0,
    ) -> MaintenanceRecoveryResult:
        """Reboot the router through the body-less GET frontend variant.

        The action is deliberately considered successful only after management
        recovers and router `boot_time` proves a new boot. A timeout or lost
        HTTP response during the reboot action is expected/inconclusive.

        Upstream also records a POST frontend variant. This helper currently
        uses only the body-less GET variant and remains physically gated until
        that transport is reconfirmed by the production SDK.
        """

        self._validate_recovery_args(
            action_timeout=action_timeout,
            recovery_attempts=recovery_attempts,
            recovery_delay=recovery_delay,
            recovery_timeout=recovery_timeout,
            initial_delay=initial_delay,
        )
        before = self._read_boot_time(timeout=recovery_timeout)

        action_response: dict[str, Any] | None = None
        action_error: NR2301Error | None = None
        try:
            action_response = self._client.call(
                "router",
                "router_call_reboot",
                timeout=action_timeout,
            )
        except (TransportError, ProtocolError) as exc:
            action_error = exc

        started = time.monotonic()
        if initial_delay:
            time.sleep(initial_delay)

        last_boot: int | None = None
        last_error: NR2301Error | None = None
        outage_observed = False

        for attempt in range(recovery_attempts):
            try:
                current = self._read_boot_time(timeout=recovery_timeout)
                last_boot = current
                elapsed = time.monotonic() - started

                # Strong evidence is a direct uptime reset. For a reboot issued
                # very shortly after initial boot, an observed outage plus an
                # uptime bounded by elapsed recovery time is also sufficient.
                if current < before or (
                    outage_observed
                    and current <= int(elapsed) + 10
                    and before <= int(elapsed) + 10
                ):
                    result: MaintenanceRecoveryResult = {
                        "boot_time_before": before,
                        "boot_time_after": current,
                        "outage_observed": outage_observed,
                    }
                    if action_response is not None:
                        result["action_response"] = action_response
                    if action_error is not None:
                        result["action_error"] = type(action_error).__name__
                    return result
            except NR2301Error as exc:
                outage_observed = True
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        details: dict[str, Any] = {
            "boot_time_before": before,
            "boot_time_after": last_boot,
            "outage_observed": outage_observed,
        }
        if action_error is not None:
            details["action_error"] = type(action_error).__name__
        if last_error is not None:
            details["last_recovery_error"] = type(last_error).__name__

        raise APIError(
            "router reboot could not be verified by management recovery and boot_time reset",
            method_id="router/router_call_reboot",
            response=details,
        )

    def set_timed_reboot(
        self,
        enabled: bool,
        time: str,
        repeat: int,
        *,
        timeout: float | None = None,
    ) -> TimedRebootSettings:
        """Set the automatic reboot schedule and require semantic read-back.

        ``repeat`` is the documented eight-bit mask: bits 0..6 are Sunday
        through Saturday and bit 7 represents no-repeat. Time input may use
        one- or two-digit hour/minute components because the live getter can
        return unpadded values; writes are normalized to zero-padded ``HH:MM``.
        """

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        canonical_time = self._canonical_time(time)
        if isinstance(repeat, bool) or not isinstance(repeat, int):
            raise TypeError("repeat must be an int")
        if not 0 <= repeat <= 0xFF:
            raise ValueError("repeat must be between 0 and 255")

        expected = {
            "enable": 1 if enabled else 0,
            "time": canonical_time,
            "repeat": repeat,
        }

        current = self.timed_reboot(timeout=timeout)
        current_fields = self._settings_fields(current)
        if current_fields == expected:
            return current

        self._client.call(
            "router",
            "router_set_timed_reboot",
            data=expected,
            timeout=timeout,
        )

        verified = self.timed_reboot(timeout=timeout)
        actual = self._settings_fields(verified)
        if actual != expected:
            raise APIError(
                "router/router_set_timed_reboot could not be verified by semantic read-back",
                method_id="router/router_set_timed_reboot",
                response={"expected": expected, "actual": actual},
            )
        return verified

    def _read_boot_time(self, *, timeout: float) -> int:
        runtime = self._client.device.runtime(timeout=timeout)
        value = runtime.get("boot_time")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProtocolError(
                "router/get_runtime_info did not return a usable boot_time"
            )
        return value

    def _recover_boot_time(
        self,
        *,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
    ) -> tuple[int, bool]:
        outage_observed = False
        last_error: NR2301Error | None = None

        for attempt in range(recovery_attempts):
            try:
                return (
                    self._read_boot_time(timeout=recovery_timeout),
                    outage_observed,
                )
            except NR2301Error as exc:
                outage_observed = True
                last_error = exc
                last_error = self._try_relogin(last_error)

            if attempt + 1 < recovery_attempts and recovery_delay:
                time.sleep(recovery_delay)

        raise APIError(
            "router management did not recover after maintenance action",
            response={
                "outage_observed": outage_observed,
                "last_recovery_error": (
                    type(last_error).__name__ if last_error is not None else None
                ),
            },
        )

    def _try_relogin(self, previous_error: NR2301Error) -> NR2301Error:
        if self._client.password is None:
            return previous_error
        try:
            self._client.login()
        except NR2301Error as login_exc:
            return login_exc
        return previous_error

    @staticmethod
    def _validate_recovery_args(
        *,
        action_timeout: float,
        recovery_attempts: int,
        recovery_delay: float,
        recovery_timeout: float,
        initial_delay: float,
    ) -> None:
        if action_timeout <= 0:
            raise ValueError("action_timeout must be greater than zero")
        if recovery_attempts <= 0:
            raise ValueError("recovery_attempts must be greater than zero")
        if recovery_delay < 0:
            raise ValueError("recovery_delay must not be negative")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than zero")
        if initial_delay < 0:
            raise ValueError("initial_delay must not be negative")

    @staticmethod
    def _canonical_time(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError(
                "time must use a valid 24-hour H:M/HH:MM representation"
            )
        match = _TIME_RE.fullmatch(value)
        if match is None:
            raise ValueError(
                "time must use a valid 24-hour H:M/HH:MM representation"
            )
        hour = int(match.group(1))
        minute = int(match.group(2))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(
                "time must use a valid 24-hour H:M/HH:MM representation"
            )
        return f"{hour:02d}:{minute:02d}"

    @classmethod
    def _settings_fields(cls, response: TimedRebootSettings) -> dict[str, Any]:
        enable = response.get("enable")
        time = response.get("time")
        repeat = response.get("repeat")

        if enable not in {0, 1} or isinstance(enable, bool):
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'enable'"
            )
        try:
            canonical_time = cls._canonical_time(time)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'time'"
            ) from exc
        if isinstance(repeat, bool) or not isinstance(repeat, int) or not 0 <= repeat <= 0xFF:
            raise ProtocolError(
                "router/router_get_timed_reboot returned invalid 'repeat'"
            )

        return {"enable": enable, "time": canonical_time, "repeat": repeat}
