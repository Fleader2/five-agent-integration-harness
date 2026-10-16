"""Cross-orchestration calibration-evidence cache, keyed by the stable identity of a module's
own standalone structure, boundary treatment, calibration dataset references, and the Agent
3/4 contract/policy versions in effect (task instructions §4) -- never by ``run_id`` (that is
``app.harness.module_calibration.run_module_calibration_workflow``'s own, separate, narrower
replay-by-run-id mechanism, unaffected by this cache).

**Never caches an infrastructure failure.** A caller simply never calls ``put`` for one (see
``orchestration.py``) -- a retry after the underlying problem is fixed must be free to actually
re-run, exactly like ``run_module_calibration_workflow``'s own identical discipline.

**Automatic Functional-Evaluation Selection and Caching increment:** ``FileCalibrationEvidence
Cache`` itself is already a generic ``cache_key -> JSON dict`` file store with no calibration-
specific logic in ``get``/``put`` -- reused verbatim (pointed at a separate ``cache_dir``) for
functional-evaluation evidence too, never duplicated. ``functional_evaluation_cache_key_for``
is the one new, functional-evaluation-specific piece: an analogous stable-identity function
naming boundary *species* and the perturbation-target battery instead of declared boundary
ports and calibration dataset references (and the Agent 3-only, never Agent-4, policy-version
set -- see ``_FUNCTIONAL_EVALUATION_CACHE_KEY_POLICY_VERSIONS``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.harness.version import (
    AGENT3_CONTRACT_VERSION,
    AGENT4_CONTRACT_VERSION,
    FUNCTIONAL_EVALUATION_WORKFLOW_POLICY_VERSION,
    MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION,
    RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION,
)

#: Baked directly into every cache key -- bumping any of these (a real Agent 3/Agent 4
#: contract change, or either of this harness's own mapping/cache-key policies) automatically
#: invalidates every previously-cached entry, never silently reusing evidence produced under a
#: since-changed policy.
_CACHE_KEY_POLICY_VERSIONS: tuple[str, str, str, str] = (
    MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION,
    AGENT3_CONTRACT_VERSION,
    AGENT4_CONTRACT_VERSION,
    RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION,
)

#: Automatic Functional-Evaluation Selection and Caching increment -- the identical "bump any
#: of these, invalidate every cached entry" discipline as ``_CACHE_KEY_POLICY_VERSIONS`` above,
#: but naming only the versions a functional-evaluation round trip actually depends on (never
#: ``AGENT4_CONTRACT_VERSION`` -- no Agent 4 call is ever involved).
_FUNCTIONAL_EVALUATION_CACHE_KEY_POLICY_VERSIONS: tuple[str, str, str] = (
    FUNCTIONAL_EVALUATION_WORKFLOW_POLICY_VERSION,
    AGENT3_CONTRACT_VERSION,
    RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION,
)


def cache_key_for(
    content_key_pairs: list[list[str]],
    boundary_ports: list[dict[str, Any]],
    calibration_dataset_references: list[dict[str, Any]],
) -> str:
    """A deterministic, stable identity for one module's own calibration evidence --
    independent of which candidate/generation/run_id produced it. Two modules with identical
    content, identical declared boundary treatment, and identical dataset references always
    produce the identical key (and therefore reuse the identical cached evidence); a change to
    any one of those -- or to this harness's own recorded Agent 3/4 contract/policy versions --
    always produces a different key.
    """
    canonical = {
        "content_key": sorted((pair[0], pair[1]) for pair in content_key_pairs),
        "boundary_ports": sorted(
            (p["species_id"], p["direction"], bool(p["externally_controlled"]))
            for p in boundary_ports
        ),
        "calibration_dataset_references": sorted(
            d["dataset_id"] for d in calibration_dataset_references
        ),
        "policy_versions": list(_CACHE_KEY_POLICY_VERSIONS),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def functional_evaluation_cache_key_for(
    content_key_pairs: list[list[str]],
    boundary_species_ids: list[str],
    perturbation_targets: list[dict[str, Any]],
) -> str:
    """A deterministic, stable identity for one module's own functional-evaluation evidence --
    independent of which candidate/generation/run_id produced it (task instructions §3: "cache
    identity must include at minimum: canonical/submodel structure; module membership;
    boundary treatment; perturbation-target battery; relevant Agent 3 contract/policy
    version"). Two modules with identical content, identical declared boundary species, and an
    identical perturbation-target battery always produce the identical key; a change to any one
    of those -- or to this harness's own recorded Agent 3 contract/policy versions -- always
    produces a different key.
    """
    canonical = {
        "content_key": sorted((pair[0], pair[1]) for pair in content_key_pairs),
        "boundary_species_ids": sorted(boundary_species_ids),
        "perturbation_targets": sorted(
            (t["target_kind"], t["target_id"], str(t["fraction"]), bool(t["is_internal"]))
            for t in perturbation_targets
        ),
        "policy_versions": list(_FUNCTIONAL_EVALUATION_CACHE_KEY_POLICY_VERSIONS),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class FileCalibrationEvidenceCache:
    """The default, file-based cache -- one JSON file per cache key, mirroring
    ``run_module_calibration_workflow``'s own established per-run-id persistence convention,
    but keyed by stable identity instead so evidence survives and is reused *across* separate
    orchestration invocations, never just within one."""

    def __init__(self, cache_dir: str | Path) -> None:
        self._cache_dir = Path(cache_dir)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        path = self._cache_dir / f"{cache_key}.json"
        if not path.is_file():
            return None
        with open(path) as f:
            return json.load(f)

    def put(self, cache_key: str, evaluation: dict[str, Any]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{cache_key}.json"
        with open(path, "w") as f:
            json.dump(evaluation, f, indent=2)


__all__ = ["FileCalibrationEvidenceCache", "cache_key_for", "functional_evaluation_cache_key_for"]
