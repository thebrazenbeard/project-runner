from pathlib import Path

import pytest

from runner.backends import BackendResult
from runner.budgets import BudgetEnvelope
from runner.durable_dispatch import SqliteDispatchAdmissionStore
from runner.models import ExactSubject
from runner.persistent_state import SqliteBudgetStore
from runner.recursive_state import SqliteRecursiveWorkStore
from runner.work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def _work() -> WorkUnit:
    return WorkUnit(
        id="journal-root",
        root_frontier_id="frontier-journal",
        parent_work_id=None,
        inputs=(
            ExactSubject(
                repository="thebrazenbeard/project-runner",
                ref="work/public-safe-portfolio-registry-v2",
                commit="a" * 40,
                path="runner/durable_dispatch.py",
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
        payload={"mode": "execution-journal-test"},
    )


def _persist_and_admit(db: Path):
    work = _work()
    fingerprint = work_unit_fingerprint(work)
    budget = BudgetEnvelope(
        lineage_id="journal-lineage",
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

    store = SqliteDispatchAdmissionStore(db)
    admitted = store.admit(
        lineage_id=budget.lineage_id,
        work_fingerprint_value=fingerprint,
        budget_scope_id=budget.scope_id,
        expected_budget_generation=1,
        expected_work_generation=1,
        holder="worker-a",
        now=10.0,
        ttl=30.0,
    )
    store.close()
    return fingerprint, budget.lineage_id, admitted.lease.fencing_token


def _result(fingerprint: str, *, classification: str = "SUCCEEDED") -> BackendResult:
    return BackendResult(
        work_fingerprint=fingerprint,
        succeeded=classification == "SUCCEEDED",
        outputs=("result-token",) if classification == "SUCCEEDED" else (),
        evidence=("journal-test",),
        classification=classification,
    )


def test_admission_creates_restart_visible_unresolved_attempt(tmp_path: Path):
    db = tmp_path / "journal.db"
    fingerprint, lineage_id, token = _persist_and_admit(db)

    reopened = SqliteDispatchAdmissionStore(db)
    unresolved = reopened.unresolved_attempts()
    reopened.close()

    assert len(unresolved) == 1
    entry = unresolved[0]
    assert entry.lineage_id == lineage_id
    assert entry.work_fingerprint == fingerprint
    assert entry.fencing_token == token == 1
    assert entry.phase == "ADMITTED"
    assert entry.result_sha256 is None
    assert entry.last_verification_status is None


def test_result_and_verification_survive_restart_and_resolve_frontier(tmp_path: Path):
    db = tmp_path / "journal.db"
    fingerprint, lineage_id, token = _persist_and_admit(db)
    result = _result(fingerprint)

    store = SqliteDispatchAdmissionStore(db)
    store.record_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        result=result,
        recorded_at=11.0,
    )
    assert store.load_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
    ) == result
    unresolved = store.unresolved_attempts()
    assert len(unresolved) == 1
    assert unresolved[0].phase == "RESULT_RECORDED"
    store.close()

    reopened = SqliteDispatchAdmissionStore(db)
    assert reopened.load_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
    ) == result
    assert reopened.record_verification(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        status=WorkUnitStatus.OUTCOME_UNKNOWN,
        reason="postcondition readback unavailable",
        verified_at=12.0,
    ) == 1
    unresolved = reopened.unresolved_attempts()
    assert len(unresolved) == 1
    assert unresolved[0].phase == "OUTCOME_UNKNOWN"
    assert unresolved[0].last_verification_status is WorkUnitStatus.OUTCOME_UNKNOWN

    assert reopened.record_verification(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        status=WorkUnitStatus.COMPLETE,
        reason="postcondition independently verified",
        verified_at=13.0,
    ) == 2
    assert reopened.unresolved_attempts() == ()
    reopened.close()


def test_conflicting_result_cannot_overwrite_durable_attempt(tmp_path: Path):
    db = tmp_path / "journal.db"
    fingerprint, lineage_id, token = _persist_and_admit(db)

    store = SqliteDispatchAdmissionStore(db)
    first = _result(fingerprint)
    store.record_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        result=first,
        recorded_at=11.0,
    )
    store.record_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        result=first,
        recorded_at=99.0,
    )

    with pytest.raises(ValueError, match="different result"):
        store.record_result(
            lineage_id=lineage_id,
            work_fingerprint_value=fingerprint,
            fencing_token=token,
            result=_result(fingerprint, classification="TRANSPORT_FAILED"),
            recorded_at=12.0,
        )
    assert store.load_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
    ) == first
    store.close()


def test_terminal_verification_is_append_only(tmp_path: Path):
    db = tmp_path / "journal.db"
    fingerprint, lineage_id, token = _persist_and_admit(db)

    store = SqliteDispatchAdmissionStore(db)
    store.record_result(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        result=_result(fingerprint),
        recorded_at=11.0,
    )
    assert store.record_verification(
        lineage_id=lineage_id,
        work_fingerprint_value=fingerprint,
        fencing_token=token,
        status=WorkUnitStatus.COMPLETE,
        reason="verified",
        verified_at=12.0,
    ) == 1
    with pytest.raises(ValueError, match="terminal verification"):
        store.record_verification(
            lineage_id=lineage_id,
            work_fingerprint_value=fingerprint,
            fencing_token=token,
            status=WorkUnitStatus.OUTCOME_UNKNOWN,
            reason="attempt to rewrite history",
            verified_at=13.0,
        )
    store.close()


def test_attempt_integrity_tamper_fails_closed(tmp_path: Path):
    db = tmp_path / "journal.db"
    fingerprint, lineage_id, token = _persist_and_admit(db)

    store = SqliteDispatchAdmissionStore(db)
    store.connection.execute(
        """
        UPDATE execution_attempts
        SET holder = 'tampered'
        WHERE lineage_id = ? AND work_fingerprint = ? AND fencing_token = ?
        """,
        (lineage_id, fingerprint, token),
    )
    with pytest.raises(ValueError, match="attempt journal digest"):
        store.unresolved_attempts()
    store.close()
