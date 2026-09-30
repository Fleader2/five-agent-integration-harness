"""Checking a producing stage's own declared contract version before invoking the next stage.

Every check here is a pure, read-only comparison of a value already present in an artifact
(never inferred, never guessed) against the expected value recorded in
``app.harness.version.CONTRACT_VERSION_MATRIX`` -- itself copied, once, from each agent's own
committed ``version.py``. A mismatch is reported as data (``WorkflowStatus.CONTRACT_MISMATCH``),
and the harness stops before ever invoking the downstream stage against a contract shape it was
not built to expect.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractCheckResult:
    boundary_name: str
    field_path: str
    expected_version: str
    actual_version: str | None
    matches: bool


def _read_field_path(artifact: dict, field_path: str) -> object | None:
    value: object = artifact
    for part in field_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def check_contract_version(
    artifact: dict, *, boundary_name: str, field_path: str, expected_version: str
) -> ContractCheckResult:
    """``ContractCheckResult.matches`` is ``False`` both when the field is present but wrong,
    and when the field is entirely absent (a missing contract-version field is itself a
    contract violation, never treated as "no opinion, assume compatible")."""
    actual = _read_field_path(artifact, field_path)
    actual_str = actual if isinstance(actual, str) else None
    return ContractCheckResult(
        boundary_name=boundary_name,
        field_path=field_path,
        expected_version=expected_version,
        actual_version=actual_str,
        matches=actual_str == expected_version,
    )


__all__ = ["ContractCheckResult", "check_contract_version"]
