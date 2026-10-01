"""The harness's own contract version and the version matrix it checks at every boundary.

The harness never invents a version number of its own for an agent's contract -- every value
below was read directly from that agent's own committed ``version.py`` (or, for Agent 1, its
``app/agent1/types.py``) at the time this harness was built. A mismatch between an artifact's
own declared version and the value recorded here is exactly what ``app.harness.contracts``
detects and reports as ``WorkflowStatus.CONTRACT_MISMATCH`` -- never silently ignored, never
auto-upgraded.

**Five-Agent Workflow V1 Hardening increment:** Agents 3, 4, and 5 each previously declared
their own name (``"agent2-to-agent3-v1"``, ``"agent2-agent3-to-agent4-v1"``,
``"agent2-agent4-to-agent5-v1"``) for what was already the identical real Agent 2 downstream
artifact shape. All three now expect the one canonical ``AGENT2_DOWNSTREAM_CONTRACT_VERSION``
Agent 2's own ``app.agent2.pipeline`` emits (``"agent2-downstream-v1"``) -- the harness no
longer needs, and no longer performs, any re-stamping of this field anywhere
(``app.harness.adapters`` passes ``agent2_model`` through byte-for-byte unchanged at every
boundary).
"""

from __future__ import annotations

HARNESS_CONTRACT_VERSION = "0.2"

#: ``agent1-biochemical-curator/app/agent1/types.py`` -- ``AGENT1_CONTRACT_VERSION``.
AGENT1_CONTRACT_VERSION = "1.5"

#: ``agent2-antimony-builder/app/agent2/version.py`` -- ``AGENT1_HANDOFF_VERSION`` (what Agent
#: 2 itself expects an incoming Agent 1 view to declare).
AGENT2_EXPECTED_AGENT1_VERSION = "1.5"

#: ``agent2-antimony-builder/app/agent2/version.py`` -- ``AGENT2_CONTRACT_VERSION`` (Agent 2's
#: own ``ModelSpecification``/``FullAntimonyArtifact`` contract version -- not itself checked
#: by any downstream agent's handoff parser, but recorded for traceability).
AGENT2_CONTRACT_VERSION = "0.12"

#: ``agent2-antimony-builder/app/agent2/version.py`` -- ``AGENT2_DOWNSTREAM_CONTRACT_VERSION``.
#: The one canonical name Agent 2's own ``app.agent2.pipeline.run_agent2_pipeline`` emits, and
#: the single value every downstream boundary below now checks for.
AGENT2_DOWNSTREAM_CONTRACT_VERSION = "agent2-downstream-v1"

#: ``agent3-simulation-diagnostics/app/agent3/version.py`` -- ``AGENT2_HANDOFF_CONTRACT_VERSION``
#: (what Agent 3 itself expects the ``contract_version`` field to say).
AGENT3_EXPECTED_AGENT2_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent3-simulation-diagnostics/app/agent3/version.py`` -- ``AGENT3_CONTRACT_VERSION``.
AGENT3_CONTRACT_VERSION = "0.1"

#: ``agent4-calibration-estimator/app/agent4/version.py`` -- ``AGENT4_HANDOFF_CONTRACT_VERSION``
#: (what Agent 4 itself expects the ``agent2_model.contract_version`` field to say).
AGENT4_EXPECTED_HANDOFF_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent4-calibration-estimator/app/agent4/version.py`` -- ``AGENT4_CONTRACT_VERSION``.
AGENT4_CONTRACT_VERSION = "0.1"

#: ``agent5-validation-experimental-design/app/agent5/version.py`` --
#: ``AGENT5_HANDOFF_CONTRACT_VERSION`` (what Agent 5 itself expects the
#: ``agent2_model.contract_version`` field to say).
AGENT5_EXPECTED_HANDOFF_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent5-validation-experimental-design/app/agent5/version.py`` -- ``AGENT5_CONTRACT_VERSION``.
AGENT5_CONTRACT_VERSION = "0.1"


#: One row per boundary this harness crosses: ``(boundary_name, artifact_field_path,
#: expected_value)``. ``artifact_field_path`` is a dotted path into the JSON artifact the
#: *producing* stage wrote, read by ``app.harness.contracts.check_contract_version`` before the
#: *consuming* stage is ever invoked.
CONTRACT_VERSION_MATRIX: tuple[tuple[str, str, str], ...] = (
    ("agent1_to_agent2", "contract_version", AGENT2_EXPECTED_AGENT1_VERSION),
    # Agent 3's own input artifact IS the agent2_model dict (no wrapping) -- Agent 4's/Agent
    # 5's own input artifacts wrap it under an "agent2_model" key alongside the other agent's
    # own report, per each one's documented handoff contract. All three now check for the
    # identical AGENT2_DOWNSTREAM_CONTRACT_VERSION value.
    ("agent2_to_agent3", "contract_version", AGENT3_EXPECTED_AGENT2_VERSION),
    ("agent2_agent3_to_agent4", "agent2_model.contract_version", AGENT4_EXPECTED_HANDOFF_VERSION),
    ("agent2_agent4_to_agent5", "agent2_model.contract_version", AGENT5_EXPECTED_HANDOFF_VERSION),
)

__all__ = [
    "AGENT1_CONTRACT_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "AGENT2_DOWNSTREAM_CONTRACT_VERSION",
    "AGENT2_EXPECTED_AGENT1_VERSION",
    "AGENT3_CONTRACT_VERSION",
    "AGENT3_EXPECTED_AGENT2_VERSION",
    "AGENT4_CONTRACT_VERSION",
    "AGENT4_EXPECTED_HANDOFF_VERSION",
    "AGENT5_CONTRACT_VERSION",
    "AGENT5_EXPECTED_HANDOFF_VERSION",
    "CONTRACT_VERSION_MATRIX",
    "HARNESS_CONTRACT_VERSION",
]
