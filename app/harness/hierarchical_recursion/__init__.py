"""Automatic Hierarchical Recursive Modularization: the harness's own second recursion
dimension -- depth into nested submodules -- on top of the existing, unchanged flat
``app.harness.recursive_candidate_search`` (one call per hierarchy node) and Agent 2's own
existing ``materialize_submodel``/``build_submodel`` (never duplicated or reimplemented here).

Public API: ``run_hierarchical_recursive_modularization``,
``resume_hierarchical_recursive_modularization`` (``orchestration``); ``serialize_checkpoint``,
``deserialize_checkpoint`` (``serialization``); every type (``types``);
``HierarchicalRecursionError``, ``HierarchicalRecursionCheckpointError`` (``errors``).

**Human-review/resume increment:** a paused run (``HierarchicalRecursionPolicy
.require_human_review=True``) now produces a serializable ``HierarchyCheckpoint`` (attached to
the returned ``HierarchicalRecursionResult.checkpoint``), and
``resume_hierarchical_recursive_modularization`` continues from exactly that point given a
caller's own approve/reject decisions, never rerunning a completed node or searching a
rejected module.
"""

from __future__ import annotations

from app.harness.hierarchical_recursion.errors import (
    HierarchicalRecursionCheckpointError,
    HierarchicalRecursionError,
)
from app.harness.hierarchical_recursion.orchestration import (
    resume_hierarchical_recursive_modularization,
    run_hierarchical_recursive_modularization,
)
from app.harness.hierarchical_recursion.serialization import (
    deserialize_checkpoint,
    deserialize_node_record,
    serialize_checkpoint,
    serialize_node_record,
)
from app.harness.hierarchical_recursion.types import (
    HierarchicalRecursionPolicy,
    HierarchicalRecursionResult,
    HierarchyBranchStoppingReason,
    HierarchyCheckpoint,
    HierarchyNodeRecord,
    HumanReviewDecision,
)

__all__ = [
    "HierarchicalRecursionCheckpointError",
    "HierarchicalRecursionError",
    "HierarchicalRecursionPolicy",
    "HierarchicalRecursionResult",
    "HierarchyBranchStoppingReason",
    "HierarchyCheckpoint",
    "HierarchyNodeRecord",
    "HumanReviewDecision",
    "deserialize_checkpoint",
    "deserialize_node_record",
    "resume_hierarchical_recursive_modularization",
    "run_hierarchical_recursive_modularization",
    "serialize_checkpoint",
    "serialize_node_record",
]
