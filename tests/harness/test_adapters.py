"""Tests for ``app.harness.adapters``."""

from __future__ import annotations

from app.harness.adapters import (
    agent3_report_to_diagnostics_view,
    build_agent4_handoff,
    build_agent5_handoff,
)
from app.harness.version import AGENT4_EXPECTED_HANDOFF_VERSION, AGENT5_EXPECTED_HANDOFF_VERSION

_AGENT2_MODEL = {"contract_version": "agent2-to-agent3-v1", "model_id": "m1", "species": []}


def test_agent3_report_to_diagnostics_view_extracts_expected_fields():
    agent3_report = {
        "report_id": "r1",
        "agent3_contract_version": "0.1",
        "agent2_model_id": "m1",
        "overall_status": "SUCCESS",
        "diagnostics": [
            {
                "finding_id": "f1",
                "category": "MODEL_STRUCTURE",
                "severity": "WARNING",
                "summary": "s",
                "related_species_ids": ["S1"],
            }
        ],
        "heuristic_parameter_ids": ["k1"],
        "placeholder_parameter_ids": [],
        "agent2_unresolved_reaction_ids": [],
        "agent2_unresolved_kinetic_law_ids": [],
        "sufficient_for_agent4": True,
    }
    view = agent3_report_to_diagnostics_view(agent3_report)
    assert view["report_id"] == "r1"
    assert view["diagnostics"][0]["related_species_ids"] == ["S1"]
    assert view["heuristic_parameter_ids"] == ["k1"]


def test_build_agent4_handoff_restamps_contract_version_only():
    agent3_report = {
        "report_id": "r1",
        "agent3_contract_version": "0.1",
        "agent2_model_id": "m1",
        "overall_status": "SUCCESS",
        "diagnostics": [],
        "heuristic_parameter_ids": [],
        "placeholder_parameter_ids": [],
        "agent2_unresolved_reaction_ids": [],
        "agent2_unresolved_kinetic_law_ids": [],
        "sufficient_for_agent4": True,
    }
    handoff = build_agent4_handoff(_AGENT2_MODEL, agent3_report)
    assert handoff["agent2_model"]["contract_version"] == AGENT4_EXPECTED_HANDOFF_VERSION
    # Every other field is untouched.
    assert handoff["agent2_model"]["model_id"] == "m1"
    assert handoff["agent2_model"]["species"] == []
    # The original dict passed in is never mutated.
    assert _AGENT2_MODEL["contract_version"] == "agent2-to-agent3-v1"


def test_build_agent5_handoff_restamps_contract_version_only():
    agent4_report = {"calibration": {"parameter_estimates": []}}
    handoff = build_agent5_handoff(_AGENT2_MODEL, agent4_report)
    assert handoff["agent2_model"]["contract_version"] == AGENT5_EXPECTED_HANDOFF_VERSION
    assert handoff["agent4_report"] == agent4_report
    assert _AGENT2_MODEL["contract_version"] == "agent2-to-agent3-v1"
