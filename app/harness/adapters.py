"""Building each downstream stage's own input artifact from upstream stage outputs.

Every function here performs exactly the field-subset/wrapping transformation each downstream
agent's own documented contract requires -- never a new judgment, never a recomputed finding.
This is the one place the harness's own code touches artifact *shape* (as opposed to simply
copying a file byte-for-byte), and each transformation here is a direct mirror of what that
agent's own contract documentation (``docs/02_*_contract.md`` in the relevant sibling
repository) already specifies as the expected input shape.
"""

from __future__ import annotations

from app.harness.version import AGENT4_EXPECTED_HANDOFF_VERSION, AGENT5_EXPECTED_HANDOFF_VERSION


def _restamp_contract_version(agent2_model: dict, expected_version: str) -> dict:
    """A shallow copy of ``agent2_model`` with its own ``contract_version`` field re-stamped to
    the exact value the specific downstream consumer it is being handed to documents as its own
    expected handoff contract version.

    **Why this is needed, and why it is not "silently repairing an agent's output":** Agent 3,
    Agent 4, and Agent 5 each independently declared their own name for what is, today,
    structurally the identical ``agent2_model`` artifact shape (confirmed this session: Agent
    3 expects ``"agent2-to-agent3-v1"``, Agent 4 expects ``"agent2-agent3-to-agent4-v1"``, Agent
    5 expects ``"agent2-agent4-to-agent5-v1"``) -- there is no single canonical version string
    the one real artifact Agent 2 actually produces can simultaneously satisfy for all three
    consumers at once, because no producer-side function in Agent 2 currently stamps a
    consumer-specific version at all. Neither Agent 4's nor Agent 5's own handoff code actually
    *enforces* this field today (both are documented Version 1 no-op placeholders -- see
    ``docs/02_contract_version_matrix.md``), so this re-stamp changes no runtime behavior in
    either agent; it only makes the artifact's own self-description honestly match the contract
    boundary it is actually crossing. Every other field -- every species, reaction, parameter,
    kinetic law, and assumption -- is passed through completely unmodified.
    """
    return {**agent2_model, "contract_version": expected_version}


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
    """The full two-key Agent 2/Agent 3 -> Agent 4 handoff dict."""
    return {
        "agent2_model": _restamp_contract_version(agent2_model, AGENT4_EXPECTED_HANDOFF_VERSION),
        "agent3_diagnostics": agent3_report_to_diagnostics_view(agent3_report),
    }


def build_agent5_handoff(agent2_model: dict, agent4_report: dict) -> dict:
    """The full two-key Agent 2/Agent 4 -> Agent 5 handoff dict -- Agent 5's own contract is
    literally Agent 4's own report shape, carried through unmodified (see
    ``agent5-validation-experimental-design/docs/02_agent4_to_agent5_contract.md``)."""
    return {
        "agent2_model": _restamp_contract_version(agent2_model, AGENT5_EXPECTED_HANDOFF_VERSION),
        "agent4_report": agent4_report,
    }


__all__ = ["agent3_report_to_diagnostics_view", "build_agent4_handoff", "build_agent5_handoff"]
