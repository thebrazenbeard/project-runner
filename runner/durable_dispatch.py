from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
from pathlib import Path
import sqlite3

from .budgets import BudgetEnvelope
from .leases import Lease
from .persistent_state import _SCHEMA as _PERSISTENT_SCHEMA
from .persistent_state import _migrate_budget_scope_schema
from .recursive_state import (
    _ALLOWED_STATUS_TRANSITIONS,
    _SCHEMA as _RECURSIVE_SCHEMA,
    _immutable_digest,
    _migrate_recursive_capability_schema,
    _normalize_capabilities,
    _work_from_payload,
)
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


@dataclass(frozen=True)
class DurableDispatchAdmission:
    work: WorkUnit
    lease: Lease
    budget_after: BudgetEnvelope
    budget_generation: int
    work_generation: int
    retry_consumed: int


class SqliteDispatchAdmissionStore:
    """Atomically reserve execution budget, claim the lease, and mark work CLAIMED."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.executescript(_PERSISTENT_SCHEMA)
            _migrate_budget_scope_schema(self.connection)
            self.connection.executescript(_RECURSIVE_SCHEMA)
            _migrate_recursive_capability_schema(self.connection)
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def admit(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        budget_scope_id: str,
        expected_budget_generation: int,
        expected_work_generation: int,
        holder: str,
        now: float,
        ttl: float,
    ) -> DurableDispatchAdmission:
        if not lineage_id.strip():
            raise ValueError("dispatch lineage id is required")
        if not budget_scope_id.strip():
            raise ValueError("dispatch budget scope id is required")
        if not holder.strip():
            raise ValueError("dispatch lease holder is required")
        if ttl <= 0:
            raise ValueError("dispatch lease ttl must be positive")

        try:
            self.connection.execute("BEGIN IMMEDIATE")

            work_row = self.connection.execute(
                """
                SELECT work_json, budget_scope_id, parent_fingerprint,
                       ancestry_json, effective_capabilities_json,
                       immutable_sha256, status, generation
                FROM recursive_work_state
                WHERE lineage_id = ? AND work_fingerprint = ?
                """,
                (lineage_id, work_fingerprint_value),
            ).fetchone()
            if work_row is None:
                raise ValueError("durable dispatch work state not found")

            (
                work_json,
                stored_scope_id,
                parent_fingerprint,
                ancestry_json,
                capabilities_json,
                immutable_sha256,
                raw_status,
                work_generation,
            ) = work_row
            if str(stored_scope_id) != budget_scope_id:
                raise ValueError("dispatch work/budget scope mismatch")
            if int(work_generation) != expected_work_generation:
                raise ValueError("dispatch work generation mismatch")

            expected_digest = _immutable_digest(
                work_json=str(work_json),
                lineage_id=lineage_id,
                budget_scope_id=budget_scope_id,
                parent_fingerprint=(
                    str(parent_fingerprint)
                    if parent_fingerprint is not None
                    else None
                ),
                ancestry_json=str(ancestry_json),
                effective_capabilities_json=str(capabilities_json),
            )
            if not hmac.compare_digest(str(immutable_sha256), expected_digest):
                raise ValueError("durable dispatch work state digest mismatch")

            try:
                work_payload = json.loads(str(work_json))
                capability_payload = json.loads(str(capabilities_json))
                current_status = WorkUnitStatus(str(raw_status))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError("durable dispatch work state is structurally invalid") from exc
            if not isinstance(work_payload, dict):
                raise ValueError("durable dispatch work payload is structurally invalid")
            if not isinstance(capability_payload, list):
                raise ValueError(
                    "durable dispatch capability ceiling is structurally invalid"
                )
            capabilities = _normalize_capabilities(capability_payload)
            if capability_payload != list(capabilities):
                raise ValueError("durable dispatch capability ceiling is not canonical")

            work = _work_from_payload(work_payload, status=current_status)
            if work_unit_fingerprint(work) != work_fingerprint_value:
                raise ValueError("durable dispatch semantic identity mismatch")
            if not set(work.required_capabilities).issubset(set(capabilities)):
                raise ValueError(
                    "durable dispatch requirement exceeds capability ceiling"
                )

            allowed = _ALLOWED_STATUS_TRANSITIONS.get(current_status, frozenset())
            if WorkUnitStatus.CLAIMED not in allowed:
                raise ValueError(
                    "durable work is not dispatch-admissible from "
                    f"{current_status.value}"
                )

            budget_row = self.connection.execute(
                """
                SELECT max_depth, depth, remaining_children, remaining_active,
                       remaining_retries, remaining_backend_jobs, generation
                FROM lineage_budgets
                WHERE lineage_id = ? AND scope_id = ?
                """,
                (lineage_id, budget_scope_id),
            ).fetchone()
            if budget_row is None:
                raise ValueError("durable dispatch budget not found")

            (
                max_depth,
                depth,
                remaining_children,
                remaining_active,
                remaining_retries,
                remaining_backend_jobs,
                budget_generation,
            ) = budget_row
            if int(budget_generation) != expected_budget_generation:
                raise ValueError("dispatch budget generation mismatch")
            if int(depth) != work.recursion_depth:
                raise ValueError("dispatch budget depth does not match work depth")
            if int(remaining_active) <= 0:
                raise ValueError("active budget exhausted")
            if int(remaining_backend_jobs) <= 0:
                raise ValueError("backend jobs budget exhausted")

            retry_consumed = int(
                current_status
                in {
                    WorkUnitStatus.FAILED_RETRYABLE,
                    WorkUnitStatus.OUTCOME_UNKNOWN,
                }
            )
            if retry_consumed and int(remaining_retries) <= 0:
                raise ValueError("retries budget exhausted")

            lease_row = self.connection.execute(
                """
                SELECT holder, fencing_token, expires_at, completed
                FROM leases
                WHERE work_fingerprint = ?
                """,
                (work_fingerprint_value,),
            ).fetchone()

            if lease_row is None:
                token = 1
                expires_at = now + ttl
                self.connection.execute(
                    """
                    INSERT INTO leases (
                        work_fingerprint, holder, fencing_token, expires_at, completed
                    ) VALUES (?, ?, ?, ?, 0)
                    """,
                    (work_fingerprint_value, holder, token, expires_at),
                )
            else:
                current_holder, current_token, current_expiry, completed = lease_row
                if bool(completed):
                    raise ValueError("completed work cannot be dispatched")
                if current_holder is not None and now < float(current_expiry):
                    raise ValueError("dispatch work already has an active lease")
                token = int(current_token) + 1
                expires_at = now + ttl
                self.connection.execute(
                    """
                    UPDATE leases
                    SET holder = ?, fencing_token = ?, expires_at = ?, completed = 0
                    WHERE work_fingerprint = ?
                    """,
                    (holder, token, expires_at, work_fingerprint_value),
                )

            budget_after = BudgetEnvelope(
                lineage_id=lineage_id,
                max_depth=int(max_depth),
                depth=int(depth),
                remaining_children=int(remaining_children),
                remaining_active=int(remaining_active) - 1,
                remaining_retries=int(remaining_retries) - retry_consumed,
                remaining_backend_jobs=int(remaining_backend_jobs) - 1,
                scope_id=budget_scope_id,
            )
            budget_update = self.connection.execute(
                """
                UPDATE lineage_budgets
                SET remaining_active = ?,
                    remaining_retries = ?,
                    remaining_backend_jobs = ?,
                    generation = generation + 1
                WHERE lineage_id = ?
                  AND scope_id = ?
                  AND generation = ?
                """,
                (
                    budget_after.remaining_active,
                    budget_after.remaining_retries,
                    budget_after.remaining_backend_jobs,
                    lineage_id,
                    budget_scope_id,
                    expected_budget_generation,
                ),
            )
            if budget_update.rowcount != 1:
                raise ValueError("dispatch budget generation changed during admission")

            work_update = self.connection.execute(
                """
                UPDATE recursive_work_state
                SET status = ?, generation = generation + 1
                WHERE lineage_id = ?
                  AND work_fingerprint = ?
                  AND generation = ?
                """,
                (
                    WorkUnitStatus.CLAIMED.value,
                    lineage_id,
                    work_fingerprint_value,
                    expected_work_generation,
                ),
            )
            if work_update.rowcount != 1:
                raise ValueError("dispatch work generation changed during admission")
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise ValueError("durable dispatch admission collided with state") from exc
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

        return DurableDispatchAdmission(
            work=WorkUnit(
                id=work.id,
                root_frontier_id=work.root_frontier_id,
                parent_work_id=work.parent_work_id,
                inputs=work.inputs,
                operation=work.operation,
                required_capabilities=work.required_capabilities,
                collision_keys=work.collision_keys,
                recursion_depth=work.recursion_depth,
                budget_allocation=work.budget_allocation,
                expected_outputs=work.expected_outputs,
                completion_criteria=work.completion_criteria,
                status=WorkUnitStatus.CLAIMED,
                payload=work.payload,
            ),
            lease=Lease(
                work_fingerprint=work_fingerprint_value,
                holder=holder,
                fencing_token=token,
                expires_at=expires_at,
            ),
            budget_after=budget_after,
            budget_generation=expected_budget_generation + 1,
            work_generation=expected_work_generation + 1,
            retry_consumed=retry_consumed,
        )
