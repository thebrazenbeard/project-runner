from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

from .backends import BackendResult, ExecutionBackend
from .budgets import BudgetEnvelope
from .dispatch import DispatchAttempt
from .leases import Lease, LeaseStore
from .models import Frontier
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
from .verify import EvidenceVerifier, SubjectReader, VerificationOutcome, verify_attempt
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint



_EXECUTION_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_attempts (
    lineage_id TEXT NOT NULL,
    work_fingerprint TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    holder TEXT NOT NULL,
    admitted_at REAL NOT NULL,
    budget_generation INTEGER NOT NULL,
    work_generation INTEGER NOT NULL,
    attempt_sha256 TEXT NOT NULL,
    result_json TEXT,
    result_sha256 TEXT,
    result_recorded_at REAL,
    PRIMARY KEY (lineage_id, work_fingerprint, fencing_token)
);

CREATE TABLE IF NOT EXISTS execution_verifications (
    lineage_id TEXT NOT NULL,
    work_fingerprint TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    verified_at REAL NOT NULL,
    verification_sha256 TEXT NOT NULL,
    PRIMARY KEY (lineage_id, work_fingerprint, fencing_token, sequence),
    FOREIGN KEY (lineage_id, work_fingerprint, fencing_token)
        REFERENCES execution_attempts (lineage_id, work_fingerprint, fencing_token)
);
"""


@dataclass(frozen=True)
class DurableExecutionJournalEntry:
    lineage_id: str
    work_fingerprint: str
    fencing_token: int
    holder: str
    admitted_at: float
    budget_generation: int
    work_generation: int
    phase: str
    result_sha256: str | None
    last_verification_status: WorkUnitStatus | None
    last_verification_reason: str | None


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _attempt_digest(
    *,
    lineage_id: str,
    work_fingerprint_value: str,
    fencing_token: int,
    holder: str,
    admitted_at: float,
    budget_generation: int,
    work_generation: int,
) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "admitted_at": admitted_at,
                "budget_generation": budget_generation,
                "fencing_token": fencing_token,
                "holder": holder,
                "lineage_id": lineage_id,
                "work_fingerprint": work_fingerprint_value,
                "work_generation": work_generation,
            }
        )
    )


def _result_payload(result: BackendResult) -> str:
    return _canonical_json(
        {
            "classification": result.classification,
            "evidence": list(result.evidence),
            "outputs": list(result.outputs),
            "succeeded": result.succeeded,
            "work_fingerprint": result.work_fingerprint,
        }
    )


def _verification_digest(
    *,
    status: WorkUnitStatus,
    reason: str,
    verified_at: float,
) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "reason": reason,
                "status": status.value,
                "verified_at": verified_at,
            }
        )
    )


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
            self.connection.executescript(_EXECUTION_JOURNAL_SCHEMA)
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

            admitted_budget_generation = expected_budget_generation + 1
            admitted_work_generation = expected_work_generation + 1
            attempt_sha256 = _attempt_digest(
                lineage_id=lineage_id,
                work_fingerprint_value=work_fingerprint_value,
                fencing_token=token,
                holder=holder,
                admitted_at=now,
                budget_generation=admitted_budget_generation,
                work_generation=admitted_work_generation,
            )
            self.connection.execute(
                """
                INSERT INTO execution_attempts (
                    lineage_id, work_fingerprint, fencing_token, holder,
                    admitted_at, budget_generation, work_generation, attempt_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lineage_id,
                    work_fingerprint_value,
                    token,
                    holder,
                    now,
                    admitted_budget_generation,
                    admitted_work_generation,
                    attempt_sha256,
                ),
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


    def _attempt_row(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        fencing_token: int,
    ):
        row = self.connection.execute(
            """
            SELECT holder, admitted_at, budget_generation, work_generation,
                   attempt_sha256, result_json, result_sha256, result_recorded_at
            FROM execution_attempts
            WHERE lineage_id = ?
              AND work_fingerprint = ?
              AND fencing_token = ?
            """,
            (lineage_id, work_fingerprint_value, fencing_token),
        ).fetchone()
        if row is None:
            raise KeyError((lineage_id, work_fingerprint_value, fencing_token))
        (
            holder,
            admitted_at,
            budget_generation,
            work_generation,
            attempt_sha256,
            result_json,
            result_sha256,
            result_recorded_at,
        ) = row
        expected_attempt_sha256 = _attempt_digest(
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
            holder=str(holder),
            admitted_at=float(admitted_at),
            budget_generation=int(budget_generation),
            work_generation=int(work_generation),
        )
        if not hmac.compare_digest(str(attempt_sha256), expected_attempt_sha256):
            raise ValueError("execution attempt journal digest mismatch")
        return (
            str(holder),
            float(admitted_at),
            int(budget_generation),
            int(work_generation),
            str(attempt_sha256),
            str(result_json) if result_json is not None else None,
            str(result_sha256) if result_sha256 is not None else None,
            float(result_recorded_at) if result_recorded_at is not None else None,
        )

    def record_result(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        fencing_token: int,
        result: BackendResult,
        recorded_at: float,
    ) -> None:
        if result.work_fingerprint != work_fingerprint_value:
            raise ValueError("backend result fingerprint does not match execution attempt")
        payload = _result_payload(result)
        payload_sha256 = _sha256_text(payload)

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self._attempt_row(
                lineage_id=lineage_id,
                work_fingerprint_value=work_fingerprint_value,
                fencing_token=fencing_token,
            )
            existing_json = row[5]
            existing_sha256 = row[6]
            if existing_json is not None or existing_sha256 is not None:
                if (
                    existing_json == payload
                    and existing_sha256 is not None
                    and hmac.compare_digest(existing_sha256, payload_sha256)
                ):
                    self.connection.rollback()
                    return
                raise ValueError("execution attempt already has a different result")

            updated = self.connection.execute(
                """
                UPDATE execution_attempts
                SET result_json = ?, result_sha256 = ?, result_recorded_at = ?
                WHERE lineage_id = ?
                  AND work_fingerprint = ?
                  AND fencing_token = ?
                  AND result_json IS NULL
                  AND result_sha256 IS NULL
                """,
                (
                    payload,
                    payload_sha256,
                    recorded_at,
                    lineage_id,
                    work_fingerprint_value,
                    fencing_token,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("execution result journal changed during recording")
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def load_result(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        fencing_token: int,
    ) -> BackendResult | None:
        row = self._attempt_row(
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
        )
        payload = row[5]
        payload_sha256 = row[6]
        if payload is None and payload_sha256 is None:
            return None
        if payload is None or payload_sha256 is None:
            raise ValueError("execution result journal is incomplete")
        expected = _sha256_text(payload)
        if not hmac.compare_digest(payload_sha256, expected):
            raise ValueError("execution result journal digest mismatch")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("execution result journal is invalid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("execution result journal payload is invalid")
        result = BackendResult(
            work_fingerprint=str(data["work_fingerprint"]),
            succeeded=bool(data["succeeded"]),
            outputs=tuple(str(item) for item in data["outputs"]),
            evidence=tuple(str(item) for item in data["evidence"]),
            classification=str(data["classification"]),
        )
        if result.work_fingerprint != work_fingerprint_value:
            raise ValueError("execution result journal fingerprint mismatch")
        return result

    def record_verification(
        self,
        *,
        lineage_id: str,
        work_fingerprint_value: str,
        fencing_token: int,
        status: WorkUnitStatus,
        reason: str,
        verified_at: float,
    ) -> int:
        allowed_statuses = {
            WorkUnitStatus.COMPLETE,
            WorkUnitStatus.FAILED_RETRYABLE,
            WorkUnitStatus.FAILED_DETERMINISTIC,
            WorkUnitStatus.OUTCOME_UNKNOWN,
            WorkUnitStatus.SUPERSEDED,
        }
        if status not in allowed_statuses:
            raise ValueError("unsupported execution verification status")
        if not reason.strip():
            raise ValueError("execution verification reason is required")
        verification_sha256 = _verification_digest(
            status=status,
            reason=reason,
            verified_at=verified_at,
        )

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self._attempt_row(
                lineage_id=lineage_id,
                work_fingerprint_value=work_fingerprint_value,
                fencing_token=fencing_token,
            )
            if row[5] is None or row[6] is None:
                raise ValueError("execution result must be recorded before verification")

            latest = self.connection.execute(
                """
                SELECT sequence, status, reason, verified_at, verification_sha256
                FROM execution_verifications
                WHERE lineage_id = ?
                  AND work_fingerprint = ?
                  AND fencing_token = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (lineage_id, work_fingerprint_value, fencing_token),
            ).fetchone()
            if latest is not None:
                (
                    latest_sequence,
                    latest_status,
                    latest_reason,
                    latest_verified_at,
                    latest_sha256,
                ) = latest
                latest_status_value = WorkUnitStatus(str(latest_status))
                latest_expected = _verification_digest(
                    status=latest_status_value,
                    reason=str(latest_reason),
                    verified_at=float(latest_verified_at),
                )
                if not hmac.compare_digest(str(latest_sha256), latest_expected):
                    raise ValueError("execution verification journal digest mismatch")
                if (
                    latest_status_value is status
                    and str(latest_reason) == reason
                    and float(latest_verified_at) == verified_at
                    and hmac.compare_digest(str(latest_sha256), verification_sha256)
                ):
                    self.connection.rollback()
                    return int(latest_sequence)
                if latest_status_value is not WorkUnitStatus.OUTCOME_UNKNOWN:
                    raise ValueError("execution attempt already has terminal verification")
                sequence = int(latest_sequence) + 1
            else:
                sequence = 1

            self.connection.execute(
                """
                INSERT INTO execution_verifications (
                    lineage_id, work_fingerprint, fencing_token, sequence,
                    status, reason, verified_at, verification_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lineage_id,
                    work_fingerprint_value,
                    fencing_token,
                    sequence,
                    status.value,
                    reason,
                    verified_at,
                    verification_sha256,
                ),
            )
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
        return sequence

    def unresolved_attempts(self) -> tuple[DurableExecutionJournalEntry, ...]:
        rows = self.connection.execute(
            """
            SELECT lineage_id, work_fingerprint, fencing_token, holder,
                   admitted_at, budget_generation, work_generation,
                   attempt_sha256, result_json, result_sha256
            FROM execution_attempts
            ORDER BY admitted_at, lineage_id, work_fingerprint, fencing_token
            """
        ).fetchall()
        unresolved: list[DurableExecutionJournalEntry] = []
        for (
            lineage_id,
            work_fingerprint_value,
            fencing_token,
            holder,
            admitted_at,
            budget_generation,
            work_generation,
            attempt_sha256,
            result_json,
            result_sha256,
        ) in rows:
            expected_attempt_sha256 = _attempt_digest(
                lineage_id=str(lineage_id),
                work_fingerprint_value=str(work_fingerprint_value),
                fencing_token=int(fencing_token),
                holder=str(holder),
                admitted_at=float(admitted_at),
                budget_generation=int(budget_generation),
                work_generation=int(work_generation),
            )
            if not hmac.compare_digest(str(attempt_sha256), expected_attempt_sha256):
                raise ValueError("execution attempt journal digest mismatch")

            latest = self.connection.execute(
                """
                SELECT status, reason, verified_at, verification_sha256
                FROM execution_verifications
                WHERE lineage_id = ?
                  AND work_fingerprint = ?
                  AND fencing_token = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (lineage_id, work_fingerprint_value, fencing_token),
            ).fetchone()

            last_status = None
            last_reason = None
            if latest is not None:
                last_status = WorkUnitStatus(str(latest[0]))
                last_reason = str(latest[1])
                latest_expected = _verification_digest(
                    status=last_status,
                    reason=last_reason,
                    verified_at=float(latest[2]),
                )
                if not hmac.compare_digest(str(latest[3]), latest_expected):
                    raise ValueError("execution verification journal digest mismatch")

            if result_json is None and result_sha256 is None:
                phase = "ADMITTED"
            elif result_json is None or result_sha256 is None:
                raise ValueError("execution result journal is incomplete")
            elif last_status is None:
                phase = "RESULT_RECORDED"
            elif last_status is WorkUnitStatus.OUTCOME_UNKNOWN:
                phase = "OUTCOME_UNKNOWN"
            else:
                continue

            if result_json is not None:
                expected_result_sha256 = _sha256_text(str(result_json))
                if not hmac.compare_digest(str(result_sha256), expected_result_sha256):
                    raise ValueError("execution result journal digest mismatch")

            unresolved.append(
                DurableExecutionJournalEntry(
                    lineage_id=str(lineage_id),
                    work_fingerprint=str(work_fingerprint_value),
                    fencing_token=int(fencing_token),
                    holder=str(holder),
                    admitted_at=float(admitted_at),
                    budget_generation=int(budget_generation),
                    work_generation=int(work_generation),
                    phase=phase,
                    result_sha256=(
                        str(result_sha256) if result_sha256 is not None else None
                    ),
                    last_verification_status=last_status,
                    last_verification_reason=last_reason,
                )
            )
        return tuple(unresolved)


def execute_admitted(
    *,
    frontier: Frontier,
    admission: DurableDispatchAdmission,
    backend: ExecutionBackend,
    journal: SqliteDispatchAdmissionStore,
    recorded_at: float,
) -> DispatchAttempt:
    """Execute one durably admitted work unit and persist its observed result.

    The admission row already exists before backend execution. If the process dies
    after a downstream effect but before record_result(), restart sees phase
    ADMITTED and must reconcile rather than blindly re-execute. Once the result is
    recorded, restart can re-verify without executing the backend again.
    """
    result = backend.execute(admission.work)
    journal.record_result(
        lineage_id=admission.budget_after.lineage_id,
        work_fingerprint_value=work_unit_fingerprint(admission.work),
        fencing_token=admission.lease.fencing_token,
        result=result,
        recorded_at=recorded_at,
    )
    return DispatchAttempt(
        frontier=frontier,
        work=admission.work,
        lease=admission.lease,
        result=result,
    )


def verify_and_record(
    attempt: DispatchAttempt,
    *,
    journal: SqliteDispatchAdmissionStore,
    lease_store: LeaseStore,
    now: float,
    current_subject_reader: SubjectReader,
    evidence_verifier: EvidenceVerifier,
    manage_lease: bool = True,
) -> VerificationOutcome:
    """Verify an observed attempt and append durable verification evidence."""
    outcome = verify_attempt(
        attempt,
        lease_store=lease_store,
        now=now,
        current_subject_reader=current_subject_reader,
        evidence_verifier=evidence_verifier,
        manage_lease=manage_lease,
    )
    if outcome.status is not WorkUnitStatus.VERIFYING:
        lineage_id = _lineage_for_attempt(journal, attempt)
        journal._attempt_row(
            lineage_id=lineage_id,
            work_fingerprint_value=work_unit_fingerprint(attempt.work),
            fencing_token=attempt.lease.fencing_token,
        )
        journal.record_verification(
            lineage_id=lineage_id,
            work_fingerprint_value=work_unit_fingerprint(attempt.work),
            fencing_token=attempt.lease.fencing_token,
            status=outcome.status,
            reason=outcome.reason,
            verified_at=now,
        )
    return outcome


def _lineage_for_attempt(
    journal: SqliteDispatchAdmissionStore,
    attempt: DispatchAttempt,
) -> str:
    row = journal.connection.execute(
        """
        SELECT lineage_id
        FROM execution_attempts
        WHERE work_fingerprint = ? AND fencing_token = ?
        """,
        (work_unit_fingerprint(attempt.work), attempt.lease.fencing_token),
    ).fetchone()
    if row is None:
        raise KeyError(
            (work_unit_fingerprint(attempt.work), attempt.lease.fencing_token)
        )
    return str(row[0])
