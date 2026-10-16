"""Automatic Hierarchical Recursive Modularization: the harness's own second recursion
dimension -- depth into nested submodules -- on top of the existing, unchanged flat
``app.harness.recursive_candidate_search`` (one call per hierarchy node) and Agent 2's own
existing ``materialize_submodel``/``build_submodel`` (never duplicated or reimplemented here).

Public API: ``run_hierarchical_recursive_modularization`` (``orchestration``); every type
(``types``); ``HierarchicalRecursionError`` (``errors``).
"""

from __future__ import annotations

from app.harness.hierarchical_recursion.errors import HierarchicalRecursionError
from app.harness.hierarchical_recursion.orchestration import (
    run_hierarchical_recursive_modularization,
)
from app.harness.hierarchical_recursion.types import (
    HierarchicalRecursionPolicy,
    HierarchicalRecursionResult,
    HierarchyBranchStoppingReason,
    HierarchyNodeRecord,
)

__all__ = [
    "HierarchicalRecursionError",
    "HierarchicalRecursionPolicy",
    "HierarchicalRecursionResult",
    "HierarchyBranchStoppingReason",
    "HierarchyNodeRecord",
    "run_hierarchical_recursive_modularization",
]
