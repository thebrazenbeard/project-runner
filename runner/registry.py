from __future__ import annotations

from pathlib import Path
from typing import Iterable, TypeVar

import yaml

from .models import DependencyEdge, Observation, ProjectDefinition, WorkerDefinition
from .schema import validate_document


T = TypeVar("T")


def _load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _reject_duplicate_ids(records: Iterable[T], kind: str) -> tuple[T, ...]:
    seen: set[str] = set()
    result: list[T] = []
    for record in records:
        record_id = getattr(record, "id")
        if record_id in seen:
            raise ValueError(f"duplicate {kind} id: {record_id}")
        seen.add(record_id)
        result.append(record)
    return tuple(result)


def load_workers(path: Path) -> tuple[WorkerDefinition, ...]:
    payload = _load_yaml(path)
    validate_document("worker", payload)
    assert isinstance(payload, dict)
    workers = (WorkerDefinition.from_mapping(item) for item in payload["workers"])
    return _reject_duplicate_ids(workers, "worker")


def load_projects(
    path: Path,
    *,
    require_scope_metadata: bool = False,
) -> tuple[ProjectDefinition, ...]:
    try:
        payload = _load_yaml(path)
        validate_document("project", payload)
        assert isinstance(payload, dict)

        if require_scope_metadata:
            required_scope_fields = {"assignment_scope", "review_scope", "family_id"}
            if any(
                not required_scope_fields.issubset(item)
                for item in payload["projects"]
            ):
                raise ValueError(
                    "external project registry requires explicit "
                    "assignment_scope, review_scope, and family_id"
                )

        projects = (ProjectDefinition.from_mapping(item) for item in payload["projects"])
        return _reject_duplicate_ids(projects, "project")
    except Exception as exc:
        if require_scope_metadata:
            safe_scope_error = (
                "external project registry requires explicit "
                "assignment_scope, review_scope, and family_id"
            )
            if isinstance(exc, ValueError) and str(exc) == safe_scope_error:
                raise ValueError(safe_scope_error) from None
            raise ValueError(
                "external project registry is unavailable or structurally invalid"
            ) from None
        raise


def load_dependencies(path: Path) -> tuple[DependencyEdge, ...]:
    payload = _load_yaml(path)
    validate_document("dependency", payload)
    assert isinstance(payload, dict)
    edges = (DependencyEdge.from_mapping(item) for item in payload["dependencies"])
    return _reject_duplicate_ids(edges, "dependency")


def load_observations(path: Path) -> tuple[Observation, ...]:
    payload = _load_yaml(path)
    validate_document("observation", payload)
    assert isinstance(payload, dict)
    return tuple(Observation.from_mapping(item) for item in payload["observations"])
