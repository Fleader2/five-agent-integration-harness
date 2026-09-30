#!/usr/bin/env python3
"""Stage runner for Agent 1 -- executed with Agent 1's own venv interpreter, with
``cwd``/``PYTHONPATH`` set to Agent 1's own repository root.

Usage: ``run_agent1.py --organism-id <uuid> --output <stage1_output.json>``

Calls Agent 1's own real, documented, read-only entrypoint chain
(``get_agent1_knowledge_package`` -> ``get_agent1_curated_knowledge_view``) against the live,
already-curated database -- no network/LLM call is made, no row is written, and no field is
invented: every value in the output artifact is a direct field of a real, already-persisted
Agent 1 record.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import decimal
import enum
import json
import uuid


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(type(obj), "__mapper__"):
        # A raw SQLAlchemy ORM model instance (some Agent 1 records, e.g. Compartment/Compound/
        # Reaction, are passed through from the persistence layer unreshaped -- see
        # ``app/agent1/export.py``'s own docstring on why those specific tables carry no
        # Claim/CurationState column to filter by). Serialize every real mapped column,
        # generically, via SQLAlchemy's own inspection API -- never guessing field names.
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(type(obj)).mapper
        return {col.key: _to_jsonable(getattr(obj, col.key)) for col in mapper.columns}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    return obj


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organism-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent1.export import get_agent1_curated_knowledge_view
    from app.agent1.service import get_agent1_knowledge_package
    from app.db.session import get_sessionmaker

    session = get_sessionmaker()()
    try:
        package = get_agent1_knowledge_package(session, organism_id=uuid.UUID(args.organism_id))
        view = get_agent1_curated_knowledge_view(package)
    finally:
        session.close()

    with open(args.output, "w") as f:
        json.dump(_to_jsonable(view), f, indent=2)

    print(f"agent1_contract_version={view.contract_version}")
    print(f"agent1_reaction_count={len(view.reactions)}")
    print(f"agent1_compound_count={len(view.compounds)}")
    print(f"agent1_claim_count={len(view.claims)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
