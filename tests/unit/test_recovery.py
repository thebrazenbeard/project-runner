from pathlib import Path

import pytest

from runner.backends import BackendResult
from runner.budgets import BudgetEnvelope
from runner.durable_dispatch import SqliteDispatchAdmissionStore
from runner.models import ExactSubject
from runner.persistent_state import SqliteBudgetStore, SqliteLeaseStore
from runner.recovery import (
    RecoveryAction,
    load_recovery_snapshots,
    reverify_recovery_snapshot,
)
from runner.recursive_state import SqliteRecursiveWorkStore
from runner.work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def _seed_attempt(db: Path):
    work = WorkUnit(
        id="recovery-root",
        root_frontier_id="frontier-recovery",
        parent_work_id=None,
        inputs=(
            ExactSubject(
                repository="thebrazenbeard/project-runner",
                ref="work/public-safe-portfolio-registry-v2",
                commit="a" * 40,
                path="runner/recovery.py",
            ),
        ),
        operation="INSPECT",
        required_capabilities=("read", "analyze"),
        collision_keys=("project:project-runner",),
        recursion_depth=0,
        budget_allocation={
            "children": 0,
            "active": 1,
            "retries": 1,
            "backend_jobs": 1,
        },
        expected_outputs=("backend-result",),
        completion_criteria=("verified",),
        status=WorkUnitStatus.PENDING,
        payload={"mode": "restart-recovery-test"},
    )
    fingerprint = work_unit_fingerprint(work)
    budget = BudgetEnvelope(
        lineage_id="recovery-lineage",
        max_depth=2,
        depth=0,
        remaining_children=0,
        remaining_active=1,
        remaining_retries=1,
        remaining_backend_jobs=1,
    )

    budgets = SqliteBudgetStore(db)
    assert budgets.put_initial(budget) == 1
    budgets.close()

    works = SqliteRecursiveWorkStore(db)
    works.put_initial(
        work=work,
        lineage_id=budget.lineage_id,
        budget_scope_id=budget.scope_id,
        parent_fingerprint=None,
        ancestry_fingerprints={fingerprint},
        effective_capabilities={"read", "analyze"},
    )
    works.close()

    journal = SqliteDispatchAdmissionStore(db)
    admitted = journal.admit(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        budget_scope_id=budget.scope_id,
        expected_budget_generation=1,
        expected_work_generation=1,
        holder="worker-a",
        now=10.0,
        ttl=30.0,
    )
    journal.close()
    return work, fingerprint, budget, admitted


def _result(fingerprint: str) -> BackendResult:
    return BackendResult(
        work_fingerprint=fingerprint,
        succeeded=True,
        outputs=("backend-result",),
        evidence=("durable-observation",),
        classification="SUCCEEDED",
    )


def test_admitted_restart_requires_effect_reconciliation(tmp_path: Path):
    db = tmp_path / "recovery.db"
    _, _, _, _ = _seed_attempt(db)

    snapshots = load_recovery_snapshots(db, now=11.0)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.action is RecoveryAction.RECONCILE_EFFECT
    assert snapshot.result is None
    assert snapshot.backend_reexecution_allowed is False
    assert snapshot.fence_current is True
    assert snapshot.fence_live is True

    leases = SqliteLeaseStore(db)
    with pytest.raises(ValueError, match="effect reconciliation"):
        reverify_recovery_snapshot(
            snapshot,
            lease_store=leases,
            now=11.0,
            current_subject_reader=lambda subject: subject,
            evidence_verifier=lambda work, result: True,
        )
    leases.close()


def test_recorded_result_reverifies_without_backend_execution(tmp_path: Path):
    db = tmp_path / "recovery.db"
    _, fingerprint, budget, admitted = _seed_attempt(db)

    journal = SqliteDispatchAdmissionStore(db)
    journal.record_result(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=admitted.lease.fencing_token,
        result=_result(fingerprint),
        recorded_at=11.0,
    )
    journal.close()

    snapshot = load_recovery_snapshots(db, now=12.0)[0]
    assert snapshot.action is RecoveryAction.REVERIFY_RECORDED_RESULT
    assert snapshot.result == _result(fingerprint)
    assert snapshot.backend_reexecution_allowed is False

    leases = SqliteLeaseStore(db)
    verification = reverify_recovery_snapshot(
        snapshot,
        lease_store=leases,
        now=12.0,
        current_subject_reader=lambda subject: subject,
        evidence_verifier=lambda work, result: True,
    )
    leases.close()

    assert verification.outcome.status is WorkUnitStatus.COMPLETE
    assert verification.terminalization_authorized is True


def test_recorded_result_with_expired_fence_cannot_terminalize(tmp_path: Path):
    db = tmp_path / "recovery.db"
    _, fingerprint, budget, admitted = _seed_attempt(db)

    journal = SqliteDispatchAdmissionStore(db)
    journal.record_result(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=admitted.lease.fencing_token,
        result=_result(fingerprint),
        recorded_at=11.0,
    )
    journal.close()

    snapshot = load_recovery_snapshots(db, now=50.0)[0]
    assert snapshot.fence_current is True
    assert snapshot.fence_live is False

    leases = SqliteLeaseStore(db)
    verification = reverify_recovery_snapshot(
        snapshot,
        lease_store=leases,
        now=50.0,
        current_subject_reader=lambda subject: subject,
        evidence_verifier=lambda work, result: True,
    )
    leases.close()

    assert verification.outcome.status is WorkUnitStatus.COMPLETE
    assert verification.terminalization_authorized is False
    assert "separate reconciliation" in verification.reason


def test_outcome_unknown_is_restart_visible_and_reverifiable(tmp_path: Path):
    db = tmp_path / "recovery.db"
    _, fingerprint, budget, admitted = _seed_attempt(db)

    journal = SqliteDispatchAdmissionStore(db)
    journal.record_result(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=admitted.lease.fencing_token,
        result=_result(fingerprint),
        recorded_at=11.0,
    )
    assert journal.record_verification(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=admitted.lease.fencing_token,
        status=WorkUnitStatus.OUTCOME_UNKNOWN,
        reason="current subject temporarily unavailable",
        verified_at=12.0,
    ) == 1
    journal.close()

    snapshot = load_recovery_snapshots(db, now=13.0)[0]
    assert snapshot.action is RecoveryAction.REVERIFY_OUTCOME_UNKNOWN

    leases = SqliteLeaseStore(db)
    verification = reverify_recovery_snapshot(
        snapshot,
        lease_store=leases,
        now=13.0,
        current_subject_reader=lambda subject: subject,
        evidence_verifier=lambda work, result: True,
    )
    leases.close()

    assert verification.outcome.status is WorkUnitStatus.COMPLETE
    assert verification.terminalization_authorized is True
