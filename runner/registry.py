from __future__ import annotations

from pathlib import Path
from typing import Iterable, TypeVar

import yaml

from .models import ProjectDefinition, WorkerDefinition
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


def load_projects(path: Path) -> tuple[ProjectDefinition, ...]:
    payload = _load_yaml(path)
    validate_document("project", payload)
    assert isinstance(payload, dict)
    projects = (ProjectDefinition.from_mapping(item) for item in payload["projects"])
    return _reject_duplicate_ids(projects, "project")
