from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Collection, Mapping

from .models import ExactSubject
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


_SCHEMA = """
CREATE TABLE IF NOT EXISTS recursive_work_state (
    lineage_id TEXT NOT NULL,
    work_fingerprint TEXT NOT NULL,
    work_json TEXT NOT NULL,
    budget_scope_id TEXT NOT NULL,
    parent_fingerprint TEXT,
    ancestry_json TEXT NOT NULL,
    immutable_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    generation INTEGER NOT NULL,
    PRIMARY KEY (lineage_id, work_fingerprint)
);
"""


@dataclass(frozen=True)
class StoredRecursiveWork:
    lineage_id: str
    work_fingerprint: str
    work: WorkUnit
    budget_scope_id: str
    parent_fingerprint: str | None
    ancestry_fingerprints: frozenset[str]
    generation: int


class SqliteRecursiveWorkStore:
    """Durable recursive work lineage with exact immutable-state validation."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def put_initial(
        self,
        *,
        work: WorkUnit,
        lineage_id: str,
        budget_scope_id: str,
        parent_fingerprint: str | None,
        ancestry_fingerprints: Collection[str],
    ) -> StoredRecursiveWork:
        if not lineage_id.strip():
            raise ValueError("recursive work lineage id is required")
        if not budget_scope_id.strip():
            raise ValueError("recursive work budget scope id is required")

        fingerprint = work_unit_fingerprint(work)
        ancestry = frozenset(str(item) for item in ancestry_fingerprints)
        if any(not item for item in ancestry):
            raise ValueError("recursive work ancestry contains an empty fingerprint")

        parent: StoredRecursiveWork | None = None
        if parent_fingerprint is None:
            if work.recursion_depth != 0:
                raise ValueError("non-root recursive work requires a parent fingerprint")
            if budget_scope_id != "root":
                raise ValueError("root recursive work requires the root budget scope")
            expected_ancestry = frozenset({fingerprint})
        else:
            if work.recursion_depth <= 0:
                raise ValueError("root recursive work cannot declare a parent fingerprint")
            if parent_fingerprint == fingerprint:
                raise ValueError("recursive work cannot parent itself")
            parent = self.get(lineage_id, parent_fingerprint)
            if parent is None:
                raise ValueError("recursive work parent is not durable")
            if work.recursion_depth != parent.work.recursion_depth + 1:
                raise ValueError("recursive work depth does not follow durable parent")
            expected_scope = f"work:{fingerprint}"
            if budget_scope_id != expected_scope:
                raise ValueError("child recursive work budget scope does not match work identity")
            expected_ancestry = parent.ancestry_fingerprints | {fingerprint}

        if ancestry != expected_ancestry:
            raise ValueError("recursive work ancestry does not extend durable parent exactly")

        work_json = _canonical_json(_work_payload(work))
        ancestry_json = _canonical_json(sorted(ancestry))
        immutable_sha256 = _immutable_digest(
            work_json=work_json,
            lineage_id=lineage_id,
            budget_scope_id=budget_scope_id,
            parent_fingerprint=parent_fingerprint,
            ancestry_json=ancestry_json,
        )

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(
                """
                INSERT INTO recursive_work_state (
                    lineage_id, work_fingerprint, work_json, budget_scope_id,
                    parent_fingerprint, ancestry_json, immutable_sha256,
                    status, generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    lineage_id,
                    fingerprint,
                    work_json,
                    budget_scope_id,
                    parent_fingerprint,
                    ancestry_json,
                    immutable_sha256,
                    work.status.value,
                ),
            )
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise ValueError("recursive work state already exists") from exc
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

        stored = self.get(lineage_id, fingerprint)
        assert stored is not None
        return stored

    def get(
        self,
        lineage_id: str,
        work_fingerprint_value: str,
    ) -> StoredRecursiveWork | None:
        row = self.connection.execute(
            """
            SELECT work_json, budget_scope_id, parent_fingerprint,
                   ancestry_json, immutable_sha256, status, generation
            FROM recursive_work_state
            WHERE lineage_id = ? AND work_fingerprint = ?
            """,
            (lineage_id, work_fingerprint_value),
        ).fetchone()
        if row is None:
            return None

        (
            work_json,
            budget_scope_id,
            parent_fingerprint,
            ancestry_json,
            immutable_sha256,
            raw_status,
            generation,
        ) = row

        expected_digest = _immutable_digest(
            work_json=str(work_json),
            lineage_id=lineage_id,
            budget_scope_id=str(budget_scope_id),
            parent_fingerprint=(
                str(parent_fingerprint) if parent_fingerprint is not None else None
            ),
            ancestry_json=str(ancestry_json),
        )
        if not hashlib.compare_digest(str(immutable_sha256), expected_digest):
            raise ValueError("recursive work state digest mismatch")

        try:
            work_payload = json.loads(str(work_json))
            ancestry_payload = json.loads(str(ancestry_json))
            status = WorkUnitStatus(str(raw_status))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("recursive work state is structurally invalid") from exc

        if not isinstance(work_payload, Mapping):
            raise ValueError("recursive work payload is structurally invalid")
        if not isinstance(ancestry_payload, list) or any(
            not isinstance(item, str) or not item for item in ancestry_payload
        ):
            raise ValueError("recursive work ancestry is structurally invalid")

        work = _work_from_payload(work_payload, status=status)
        observed_fingerprint = work_unit_fingerprint(work)
        if observed_fingerprint != work_fingerprint_value:
            raise ValueError("recursive work semantic identity mismatch")

        ancestry = frozenset(ancestry_payload)
        if observed_fingerprint not in ancestry:
            raise ValueError("recursive work ancestry omits current work")

        if parent_fingerprint is None:
            if work.recursion_depth != 0 or budget_scope_id != "root":
                raise ValueError("recursive root state is inconsistent")
            if ancestry != frozenset({observed_fingerprint}):
                raise ValueError("recursive root ancestry is inconsistent")
        else:
            parent_fingerprint = str(parent_fingerprint)
            if parent_fingerprint == observed_fingerprint:
                raise ValueError("recursive work cannot parent itself")
            expected_scope = f"work:{observed_fingerprint}"
            if budget_scope_id != expected_scope:
                raise ValueError("recursive child budget scope is inconsistent")
            if parent_fingerprint not in ancestry:
                raise ValueError("recursive child ancestry omits parent")

        return StoredRecursiveWork(
            lineage_id=lineage_id,
            work_fingerprint=work_fingerprint_value,
            work=work,
            budget_scope_id=str(budget_scope_id),
            parent_fingerprint=parent_fingerprint,
            ancestry_fingerprints=ancestry,
            generation=int(generation),
        )

    def compare_and_swap_status(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        expected_generation: int,
        status: WorkUnitStatus,
    ) -> StoredRecursiveWork:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            cursor = self.connection.execute(
                """
                UPDATE recursive_work_state
                SET status = ?, generation = generation + 1
                WHERE lineage_id = ?
                  AND work_fingerprint = ?
                  AND generation = ?
                """,
                (
                    status.value,
                    lineage_id,
                    work_fingerprint_value,
                    expected_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("recursive work generation mismatch")
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

        stored = self.get(lineage_id, work_fingerprint_value)
        if stored is None:
            raise ValueError("recursive work state disappeared after update")
        return stored


def _subject_payload(subject: ExactSubject) -> dict[str, str | None]:
    return {
        "repository": subject.repository,
        "ref": subject.ref,
        "commit": subject.commit,
        "path": subject.path,
        "digest": subject.digest,
    }


def _work_payload(work: WorkUnit) -> dict[str, Any]:
    return {
        "id": work.id,
        "root_frontier_id": work.root_frontier_id,
        "parent_work_id": work.parent_work_id,
        "inputs": [_subject_payload(subject) for subject in work.inputs],
        "operation": work.operation,
        "required_capabilities": list(work.required_capabilities),
        "collision_keys": list(work.collision_keys),
        "recursion_depth": work.recursion_depth,
        "budget_allocation": dict(work.budget_allocation),
        "expected_outputs": list(work.expected_outputs),
        "completion_criteria": list(work.completion_criteria),
        "payload": work.payload,
    }


def _work_from_payload(
    payload: Mapping[str, Any],
    *,
    status: WorkUnitStatus,
) -> WorkUnit:
    inputs = payload.get("inputs")
    if not isinstance(inputs, list):
        raise ValueError("recursive work inputs are structurally invalid")

    try:
        subjects = tuple(
            ExactSubject.from_mapping(item)
            for item in inputs
            if isinstance(item, Mapping)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("recursive work subjects are structurally invalid") from exc
    if len(subjects) != len(inputs):
        raise ValueError("recursive work subjects are structurally invalid")

    raw_budget = payload.get("budget_allocation")
    raw_payload = payload.get("payload")
    if not isinstance(raw_budget, Mapping) or not isinstance(raw_payload, Mapping):
        raise ValueError("recursive work mappings are structurally invalid")

    try:
        return WorkUnit(
            id=str(payload["id"]),
            root_frontier_id=str(payload["root_frontier_id"]),
            parent_work_id=(
                str(payload["parent_work_id"])
                if payload.get("parent_work_id") is not None
                else None
            ),
            inputs=subjects,
            operation=str(payload["operation"]),
            required_capabilities=tuple(str(item) for item in payload["required_capabilities"]),
            collision_keys=tuple(str(item) for item in payload["collision_keys"]),
            recursion_depth=int(payload["recursion_depth"]),
            budget_allocation={str(k): int(v) for k, v in raw_budget.items()},
            expected_outputs=tuple(str(item) for item in payload["expected_outputs"]),
            completion_criteria=tuple(str(item) for item in payload["completion_criteria"]),
            status=status,
            payload=dict(raw_payload),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("recursive work payload is structurally invalid") from exc


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _immutable_digest(
    *,
    work_json: str,
    lineage_id: str,
    budget_scope_id: str,
    parent_fingerprint: str | None,
    ancestry_json: str,
) -> str:
    payload = _canonical_json(
        {
            "work_json": work_json,
            "lineage_id": lineage_id,
            "budget_scope_id": budget_scope_id,
            "parent_fingerprint": parent_fingerprint,
            "ancestry_json": ancestry_json,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
