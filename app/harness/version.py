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

**Contract-version matrix synchronization increment:** ``AGENT1_CONTRACT_VERSION``/
``AGENT2_EXPECTED_AGENT1_VERSION`` were stale at ``"1.5"`` -- Agent 1's own
``AGENT1_CONTRACT_VERSION`` was bumped to ``"1.6"`` by its KEGG NETWORK support increment
(additive ``networks``/``network_nodes``/``network_edges``/``network_perturbations``/
``network_pathways``/``network_diseases``/``network_publications`` fields on
``Agent1KnowledgePackage``, and ``networks: tuple[CuratedNetwork, ...]`` on
``Agent1CuratedKnowledgeView``), but this harness's own copy was never updated, causing a false
``CONTRACT_MISMATCH`` against Agent 1's real, current, live output
(``tests/harness/test_real_sce00061_workflow.py``). Verified directly against Agent 2's own
runtime code (not just its docstrings) that this is a false alarm, not a true incompatibility:
Agent 2's own ``AGENT1_HANDOFF_VERSION`` constant
(``agent2-antimony-builder/app/agent2/version.py``) is itself still textually ``"1.5"`` --
apparently never bumped alongside Agent 1's own increment --
but nothing in Agent 2's actual parsing code (``app.agent2.handoff.translate``) compares an
incoming ``contract_version`` against that constant at all; it only requires the field to be
present. Agent 2 has no ``networks`` field of its own and never reads one, so a real ``"1.6"``
payload (additive fields only, nothing removed or reshaped) parses into Agent 2's existing shape
exactly as before. The two are genuinely compatible today; only this harness's own copied
bookkeeping was wrong. Agent 2's own unbumped constant is Agent 2's repository to fix, not this
harness's, and is left alone here.
"""

from __future__ import annotations

HARNESS_CONTRACT_VERSION = "0.2"

#: ``agent1-biochemical-curator/app/agent1/types.py`` -- ``AGENT1_CONTRACT_VERSION``.
AGENT1_CONTRACT_VERSION = "1.6"

#: Agent 1's own real, current, live ``AGENT1_CONTRACT_VERSION`` -- not
#: ``agent2-antimony-builder/app/agent2/version.py``'s own (stale, unenforced)
#: ``AGENT1_HANDOFF_VERSION`` constant, which still says ``"1.5"``. Confirmed by direct
#: inspection of Agent 2's actual runtime code (see module docstring) that Agent 2 does not
#: compare an incoming ``contract_version`` against that constant at all, so tracking Agent 1's
#: real value here -- rather than Agent 2's own stale, never-enforced one -- is what actually
#: reflects the two agents' real, verified compatibility.
AGENT2_EXPECTED_AGENT1_VERSION = "1.6"

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
