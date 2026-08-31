# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

SIM = Path("src/nr2301/namespaces/sim.py")
TESTS = Path("tests/test_sim_namespace.py")
CHANGELOG = Path("CHANGELOG.md")

text = SIM.read_text(encoding="utf-8")
text = text.replace("from ..exceptions import ProtocolError", "from ..exceptions import APIError, ProtocolError")
text = text.replace(
'''class SIMNamespace:\n    """Safe SIM status reads.\n\n    PIN/PUK mutations are intentionally not implemented because the public API\n    classifies those paths as static-only / do-not-test-for-coverage.\n    """''',
'''class SIMNamespace:\n    """SIM status and PIN/PUK capabilities backed by public contracts.\n\n    PIN/PUK values are secrets. Callers must not log them. Mutation helpers\n    apply a retry-budget guard by default, while the generic client transport\n    remains available for deliberately lower-level use.\n    """'''
)

anchor = '''    @staticmethod\n    def _extract_pin_puk(response: Mapping[str, Any]) -> Mapping[str, Any]:\n'''
methods = '''    def provide_pin(\n        self,\n        pin: str,\n        *,\n        timeout: float | None = None,\n        protect_retries: bool = True,\n    ) -> dict[str, Any]:\n        """Provide the current SIM PIN using the shipped-frontend payload.\n\n        The PIN is never included in SDK-generated error metadata.\n        """\n\n        pin = self._validate_secret(pin, "PIN")\n        if protect_retries:\n            self._require_retry_budget("pin", timeout=timeout)\n        return self._client.call(\n            "sim",\n            "provide_pin",\n            data={"pin_puk": {"pin": pin}},\n            timeout=timeout,\n        )\n\n    def enable_pin(\n        self,\n        pin: str,\n        *,\n        timeout: float | None = None,\n        protect_retries: bool = True,\n    ) -> dict[str, Any]:\n        """Enable SIM PIN protection using the current PIN."""\n\n        pin = self._validate_secret(pin, "PIN")\n        if protect_retries:\n            self._require_retry_budget("pin", timeout=timeout)\n        return self._client.call(\n            "sim",\n            "enable_pin",\n            data={"pin_puk": {"pin": pin}},\n            timeout=timeout,\n        )\n\n    def disable_pin(\n        self,\n        pin: str,\n        *,\n        timeout: float | None = None,\n        protect_retries: bool = True,\n    ) -> dict[str, Any]:\n        """Disable SIM PIN protection using the current PIN."""\n\n        pin = self._validate_secret(pin, "PIN")\n        if protect_retries:\n            self._require_retry_budget("pin", timeout=timeout)\n        return self._client.call(\n            "sim",\n            "disable_pin",\n            data={"pin_puk": {"pin": pin}},\n            timeout=timeout,\n        )\n\n    def change_pin(\n        self,\n        pin: str,\n        new_pin: str,\n        *,\n        timeout: float | None = None,\n        protect_retries: bool = True,\n    ) -> dict[str, Any]:\n        """Change the SIM PIN using the exact shipped-frontend payload."""\n\n        pin = self._validate_secret(pin, "PIN")\n        new_pin = self._validate_secret(new_pin, "new PIN")\n        if protect_retries:\n            self._require_retry_budget("pin", timeout=timeout)\n        return self._client.call(\n            "sim",\n            "change_pin",\n            data={"pin_puk": {"pin": pin, "new_pin": new_pin}},\n            timeout=timeout,\n        )\n\n    def reset_pin_using_puk(\n        self,\n        puk: str,\n        new_pin: str,\n        *,\n        timeout: float | None = None,\n        protect_retries: bool = True,\n    ) -> dict[str, Any]:\n        """Reset a blocked PIN using PUK plus a new PIN.\n\n        This is a recovery capability. Normal physical coverage must not\n        intentionally exhaust PIN retries merely to reach this state.\n        """\n\n        puk = self._validate_secret(puk, "PUK")\n        new_pin = self._validate_secret(new_pin, "new PIN")\n        if protect_retries:\n            self._require_retry_budget("puk", timeout=timeout)\n        return self._client.call(\n            "sim",\n            "reset_pin_using_puk",\n            data={"pin_puk": {"puk": puk, "new_pin": new_pin}},\n            timeout=timeout,\n        )\n\n    def _require_retry_budget(\n        self,\n        kind: str,\n        *,\n        timeout: float | None = None,\n    ) -> None:\n        status = self.status(timeout=timeout)\n        pin_puk = self._extract_pin_puk(status)\n        field = "puk_attempts" if kind == "puk" else "pin_attempts"\n        value = pin_puk.get(field)\n        if isinstance(value, bool):\n            value = None\n        try:\n            attempts = int(value) if value is not None else None\n        except (TypeError, ValueError):\n            attempts = None\n        if attempts is None:\n            raise APIError(\n                f"refusing SIM {kind.upper()} mutation because {field} is unavailable",\n                method_id="sim/retry_guard",\n                response={"attempt_field": field, "attempts": None},\n            )\n        if attempts <= 1:\n            raise APIError(\n                f"refusing SIM {kind.upper()} mutation to preserve the final remaining attempt",\n                method_id="sim/retry_guard",\n                response={"attempt_field": field, "attempts": attempts},\n            )\n\n    @staticmethod\n    def _validate_secret(value: str, label: str) -> str:\n        if not isinstance(value, str):\n            raise TypeError(f"{label} must be a string")\n        if not value:\n            raise ValueError(f"{label} must not be empty")\n        # maxlength=8 is the only exact input-length constraint recovered from\n        # the shipped WebUI. Do not invent a stricter minimum here.\n        if len(value) > 8:\n            raise ValueError(f"{label} exceeds the source-verified maximum length of 8")\n        return value\n\n'''
if methods.strip() not in text:
    if anchor not in text:
        raise SystemExit("SIM insertion anchor not found")
    text = text.replace(anchor, methods + anchor, 1)
SIM.write_text(text, encoding="utf-8")

# Append focused offline contract tests. Synthetic digits only; never real credentials.
tests = TESTS.read_text(encoding="utf-8")
extra = r'''

@pytest.mark.parametrize(
    ("helper", "args", "method_name", "expected_body"),
    [
        ("provide_pin", ("1234",), "provide_pin", {"pin_puk": {"pin": "1234"}}),
        ("enable_pin", ("1234",), "enable_pin", {"pin_puk": {"pin": "1234"}}),
        ("disable_pin", ("1234",), "disable_pin", {"pin_puk": {"pin": "1234"}}),
        (
            "change_pin",
            ("1234", "5678"),
            "change_pin",
            {"pin_puk": {"pin": "1234", "new_pin": "5678"}},
        ),
        (
            "reset_pin_using_puk",
            ("12345678", "5678"),
            "reset_pin_using_puk",
            {"pin_puk": {"puk": "12345678", "new_pin": "5678"}},
        ),
    ],
)
def test_sim_mutation_helpers_use_exact_frontend_payloads(helper, args, method_name, expected_body):
    client, session = authenticated_client({"response": {"setting_response": "UNKNOWN"}})

    result = getattr(client.sim, helper)(*args, protect_retries=False)
    assert result == {"response": {"setting_response": "UNKNOWN"}}

    method, _, kwargs = session.calls[0]
    assert method == "POST"
    assert kwargs["params"]["path"] == "sim"
    assert kwargs["params"]["method"] == method_name
    assert kwargs["json"] == expected_body


def test_sim_retry_guard_refuses_final_pin_attempt_without_secret_in_error():
    client, session = authenticated_client(
        {"pin_puk": {"pin_attempts": 1, "puk_attempts": 10}},
    )

    from nr2301 import APIError

    with pytest.raises(APIError) as exc_info:
        client.sim.enable_pin("8765")

    assert "8765" not in str(exc_info.value)
    assert exc_info.value.response == {"attempt_field": "pin_attempts", "attempts": 1}
    assert len(session.calls) == 1


def test_sim_retry_guard_allows_write_when_attempt_budget_is_safe():
    client, session = authenticated_client(
        {"pin_puk": {"pin_attempts": 3, "puk_attempts": 10}},
        {"response": {"setting_response": "UNKNOWN"}},
    )

    client.sim.disable_pin("1234")

    assert len(session.calls) == 2
    assert session.calls[1][2]["json"] == {"pin_puk": {"pin": "1234"}}


def test_sim_secret_validation_only_applies_source_verified_maximum():
    client, _ = authenticated_client()

    with pytest.raises(ValueError, match="maximum length of 8"):
        client.sim.provide_pin("123456789", protect_retries=False)
    with pytest.raises(ValueError, match="must not be empty"):
        client.sim.provide_pin("", protect_retries=False)
'''
if "test_sim_mutation_helpers_use_exact_frontend_payloads" not in tests:
    tests += extra
TESTS.write_text(tests, encoding="utf-8")

changelog = CHANGELOG.read_text(encoding="utf-8")
added = "- added `client.sim.provide_pin()`, `enable_pin()`, `disable_pin()`, `change_pin()` and `reset_pin_using_puk()` using the exact normalized frontend payloads; helpers never log secrets and apply a default retry-budget guard that preserves the final PIN/PUK attempt while remaining explicitly overridable for deliberate recovery use\n"
anchor_added = "### Added\n\n"
if added not in changelog:
    changelog = changelog.replace(anchor_added, anchor_added + added, 1)
backlog_old = "- research SIM PIN/PUK mutation paths deliberately on the dedicated test router without broad retry-consuming probes\n"
backlog_new = "- physically validate the new SIM PIN helpers with known locally supplied credentials and retry guards; keep PUK-reset testing recovery-only rather than manufacturing a blocked SIM merely for coverage\n"
changelog = changelog.replace(backlog_old, backlog_new)
CHANGELOG.write_text(changelog, encoding="utf-8")

print("Added SIM PIN/PUK helpers, retry guard and offline tests.")
