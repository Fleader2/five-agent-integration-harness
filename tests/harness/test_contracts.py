"""Contract-boundary tests for ``app.harness.contracts``."""

from __future__ import annotations

from app.harness.contracts import check_contract_version


def test_matching_version_passes():
    artifact = {"contract_version": "agent2-to-agent3-v1"}
    result = check_contract_version(
        artifact,
        boundary_name="agent2_to_agent3",
        field_path="contract_version",
        expected_version="agent2-to-agent3-v1",
    )
    assert result.matches is True


def test_mismatched_version_fails():
    artifact = {"contract_version": "some-other-version"}
    result = check_contract_version(
        artifact,
        boundary_name="agent2_to_agent3",
        field_path="contract_version",
        expected_version="agent2-to-agent3-v1",
    )
    assert result.matches is False
    assert result.actual_version == "some-other-version"


def test_missing_field_fails_never_assumed_compatible():
    artifact = {"some_other_key": "value"}
    result = check_contract_version(
        artifact,
        boundary_name="agent2_to_agent3",
        field_path="contract_version",
        expected_version="agent2-to-agent3-v1",
    )
    assert result.matches is False
    assert result.actual_version is None


def test_nested_dotted_field_path_resolves():
    artifact = {"agent2_model": {"contract_version": "agent2-agent3-to-agent4-v1"}}
    result = check_contract_version(
        artifact,
        boundary_name="agent2_agent3_to_agent4",
        field_path="agent2_model.contract_version",
        expected_version="agent2-agent3-to-agent4-v1",
    )
    assert result.matches is True


def test_nested_field_path_missing_intermediate_dict_fails_gracefully():
    artifact = {"agent2_model": "not-a-dict"}
    result = check_contract_version(
        artifact,
        boundary_name="agent2_agent3_to_agent4",
        field_path="agent2_model.contract_version",
        expected_version="agent2-agent3-to-agent4-v1",
    )
    assert result.matches is False
    assert result.actual_version is None
