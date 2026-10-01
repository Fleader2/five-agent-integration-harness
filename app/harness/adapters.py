"""Building each downstream stage's own input artifact from upstream stage outputs.

Every function here performs exactly the field-subset/wrapping transformation each downstream
agent's own documented contract requires -- never a new judgment, never a recomputed finding,
and (Five-Agent Workflow V1 Hardening increment) never a rewrite of any field. Agent 2's own
canonical ``run_agent2_pipeline`` entrypoint now emits exactly one ``contract_version``
(``"agent2-downstream-v1"``) that Agents 3, 4, and 5 all already expect unchanged -- the
``agent2_model`` dict these functions wrap is passed through byte-for-byte identical to what
Stage 2 itself produced, never copied or re-stamped. This is the one place the harness's own
code touches artifact *shape* (as opposed to simply copying a file byte-for-byte), and each
transformation here is a direct mirror of what that agent's own contract documentation
(``docs/02_*_contract.md`` in the relevant sibling repository) already specifies as the expected
input shape.
"""

from __future__ import annotations


def agent3_report_to_diagnostics_view(agent3_report: dict) -> dict:
    """The lightweight ``agent3_diagnostics`` view Agent 4's own handoff contract expects --
    a field-subset of Agent 3's own full report, carried through verbatim (see
    ``agent4-calibration-estimator/docs/02_agent2_agent3_to_agent4_contract.md``)."""
    return {
        "report_id": agent3_report["report_id"],
        "agent3_contract_version": agent3_report["agent3_contract_version"],
        "agent2_model_id": agent3_report["agent2_model_id"],
        "overall_status": agent3_report["overall_status"],
        "diagnostics": [
            {
                "finding_id": f["finding_id"],
                "category": f["category"],
                "severity": f["severity"],
                "summary": f["summary"],
                "related_species_ids": f.get("related_species_ids", []),
                "related_reaction_ids": f.get("related_reaction_ids", []),
                "related_parameter_ids": f.get("related_parameter_ids", []),
            }
            for f in agent3_report.get("diagnostics", [])
        ],
        "heuristic_parameter_ids": agent3_report.get("heuristic_parameter_ids", []),
        "placeholder_parameter_ids": agent3_report.get("placeholder_parameter_ids", []),
        "agent2_unresolved_reaction_ids": agent3_report.get("agent2_unresolved_reaction_ids", []),
        "agent2_unresolved_kinetic_law_ids": agent3_report.get(
            "agent2_unresolved_kinetic_law_ids", []
        ),
        "sufficient_for_agent4": agent3_report.get("sufficient_for_agent4", False),
    }


def build_agent4_handoff(agent2_model: dict, agent3_report: dict) -> dict:
    """The full two-key Agent 2/Agent 3 -> Agent 4 handoff dict. ``agent2_model`` is passed
    through exactly as Stage 2 produced it -- no copy, no field rewrite of any kind."""
    return {
        "agent2_model": agent2_model,
        "agent3_diagnostics": agent3_report_to_diagnostics_view(agent3_report),
    }


def build_agent5_handoff(agent2_model: dict, agent4_report: dict) -> dict:
    """The full two-key Agent 2/Agent 4 -> Agent 5 handoff dict -- Agent 5's own contract is
    literally Agent 4's own report shape, carried through unmodified (see
    ``agent5-validation-experimental-design/docs/02_agent4_to_agent5_contract.md``).
    ``agent2_model`` is passed through exactly as Stage 2 produced it."""
    return {
        "agent2_model": agent2_model,
        "agent4_report": agent4_report,
    }


__all__ = ["agent3_report_to_diagnostics_view", "build_agent4_handoff", "build_agent5_handoff"]
