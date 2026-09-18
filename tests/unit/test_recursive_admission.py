import sqlite3
from pathlib import Path

import pytest

from runner.budgets import BudgetEnvelope
from runner.decompose import admit_child_work
from runner.models import ExactSubject
from runner.persistent_state import SqliteBudgetStore
from runner.recursive_admission import SqliteRecursiveAdmissionStore
from runner.recursive_state import SqliteRecursiveWorkStore
from runner.work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def _work(
    work_id: str,
    *,
    depth: int,
    parent: str | None,
    commit: str,
    operation: str,
) -> WorkUnit:
    return WorkUnit(
        id=work_id,
        root_frontier_id="frontier-atomic",
        parent_work_id=parent,
        inputs=(
            ExactSubject(
                repository="thebrazenbeard/project-runner",
                ref="work/public-safe-portfolio-registry-v2",
                commit=commit,
                path="runner/recursive_admission.py",
            ),
        ),
        operation=operation,
        required_capabilities=("read", "analyze"),
        collision_keys=("project:project-runner",),
        recursion_depth=depth,
        budget_allocation={
            "children": 1,
            "active": 1,
            "retries": 0,
            "backend_jobs": 1,
        },
        expected_outputs=("verified-work",),
        completion_criteria=("exact-subject-current",),
        status=WorkUnitStatus.PENDING,
        payload={"mode": "atomic-child-admission-test"},
    )


def _root_budget() -> BudgetEnvelope:
    return BudgetEnvelope(
        lineage_id="atomic-lineage",
        max_depth=3,
        depth=0,
        remaining_children=2,
        remaining_active=2,
        remaining_retries=1,
        remaining_backend_jobs=2,
    )


def _prepare_admission():
    root = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    child = _work(
        "child",
        depth=1,
        parent=root.id,
        commit="b" * 40,
        operation="REREVIEW",
    )
    admission = admit_child_work(
        parent=root,
        child=child,
        parent_budget=_root_budget(),
        parent_capabilities={"read", "analyze"},
        target_capabilities={"read", "analyze"},
        ancestry_fingerprints=(),
        child_children=1,
        child_active=1,
        child_retries=0,
        child_backend_jobs=1,
    )
    return root, admission


def _persist_root(db: Path):
    root, admission = _prepare_admission()
    root_fingerprint = work_unit_fingerprint(root)

    budget_store = SqliteBudgetStore(db)
    assert budget_store.put_initial(_root_budget()) == 1
    budget_store.close()

    work_store = SqliteRecursiveWorkStore(db)
    work_store.put_initial(
        work=root,
        lineage_id=_root_budget().lineage_id,
        budget_scope_id="root",
        parent_fingerprint=None,
        ancestry_fingerprints={root_fingerprint},
    )
    work_store.close()
    return root, root_fingerprint, admission


def test_atomic_child_admission_commits_budget_and_work_together(tmp_path: Path):
    db = tmp_path / "state.db"
    _, root_fingerprint, admission = _persist_root(db)
    child_fingerprint = work_unit_fingerprint(admission.work)

    store = SqliteRecursiveAdmissionStore(db)
    committed = store.commit_child(
        parent_work_fingerprint=root_fingerprint,
        parent_budget_before=_root_budget(),
        expected_parent_budget_generation=1,
        admission=admission,
    )
    store.close()

    assert committed.parent_budget_generation == 2
    assert committed.child_budget_generation == 1
    assert committed.child_work_generation == 1
    assert committed.child_work_fingerprint == child_fingerprint

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    child_budget, child_generation = budgets.get(
        "atomic-lineage",
        admission.child_budget.scope_id,
    )
    assert parent_budget == admission.parent_budget
    assert parent_generation == 2
    assert child_budget == admission.child_budget
    assert child_generation == 1
    budgets.close()

    works = SqliteRecursiveWorkStore(db)
    child = works.get("atomic-lineage", child_fingerprint)
    assert child is not None
    assert child.work == admission.work
    assert child.parent_fingerprint == root_fingerprint
    assert child.ancestry_fingerprints == admission.ancestry_fingerprints
    assert child.generation == 1
    works.close()


def test_stale_parent_generation_rolls_back_without_child_state(tmp_path: Path):
    db = tmp_path / "state.db"
    _, root_fingerprint, admission = _persist_root(db)
    child_fingerprint = work_unit_fingerprint(admission.work)

    store = SqliteRecursiveAdmissionStore(db)
    with pytest.raises(ValueError, match="generation"):
        store.commit_child(
            parent_work_fingerprint=root_fingerprint,
            parent_budget_before=_root_budget(),
            expected_parent_budget_generation=0,
            admission=admission,
        )
    store.close()

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    assert parent_budget == _root_budget()
    assert parent_generation == 1
    with pytest.raises(KeyError):
        budgets.get("atomic-lineage", admission.child_budget.scope_id)
    budgets.close()

    works = SqliteRecursiveWorkStore(db)
    assert works.get("atomic-lineage", child_fingerprint) is None
    works.close()


def test_child_budget_collision_rolls_back_parent_transfer(tmp_path: Path):
    db = tmp_path / "state.db"
    _, root_fingerprint, admission = _persist_root(db)

    connection = sqlite3.connect(db)
    child = admission.child_budget
    connection.execute(
        """
        INSERT INTO lineage_budgets (
            lineage_id, scope_id, max_depth, depth,
            remaining_children, remaining_active, remaining_retries,
            remaining_backend_jobs, generation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            child.lineage_id,
            child.scope_id,
            child.max_depth,
            child.depth,
            child.remaining_children,
            child.remaining_active,
            child.remaining_retries,
            child.remaining_backend_jobs,
        ),
    )
    connection.commit()
    connection.close()

    store = SqliteRecursiveAdmissionStore(db)
    with pytest.raises(ValueError, match="collides"):
        store.commit_child(
            parent_work_fingerprint=root_fingerprint,
            parent_budget_before=_root_budget(),
            expected_parent_budget_generation=1,
            admission=admission,
        )
    store.close()

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    assert parent_budget == _root_budget()
    assert parent_generation == 1
    budgets.close()


def test_terminal_parent_cannot_admit_child_and_budget_is_unchanged(tmp_path: Path):
    db = tmp_path / "state.db"
    _, root_fingerprint, admission = _persist_root(db)

    works = SqliteRecursiveWorkStore(db)
    complete = works.compare_and_swap_status(
        lineage_id="atomic-lineage",
        work_fingerprint_value=root_fingerprint,
        expected_generation=1,
        status=WorkUnitStatus.COMPLETE,
    )
    assert complete.generation == 2
    works.close()

    store = SqliteRecursiveAdmissionStore(db)
    with pytest.raises(ValueError, match="terminal"):
        store.commit_child(
            parent_work_fingerprint=root_fingerprint,
            parent_budget_before=_root_budget(),
            expected_parent_budget_generation=1,
            admission=admission,
        )
    store.close()

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    assert parent_budget == _root_budget()
    assert parent_generation == 1
    budgets.close()


def test_missing_durable_parent_rejects_child_without_budget_transfer(tmp_path: Path):
    db = tmp_path / "state.db"
    root, admission = _prepare_admission()
    root_fingerprint = work_unit_fingerprint(root)

    budgets = SqliteBudgetStore(db)
    budgets.put_initial(_root_budget())
    budgets.close()

    store = SqliteRecursiveAdmissionStore(db)
    with pytest.raises(ValueError, match="parent work state not found"):
        store.commit_child(
            parent_work_fingerprint=root_fingerprint,
            parent_budget_before=_root_budget(),
            expected_parent_budget_generation=1,
            admission=admission,
        )
    store.close()

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    assert parent_budget == _root_budget()
    assert parent_generation == 1
    budgets.close()


def test_tampered_parent_state_rejects_child_without_budget_transfer(tmp_path: Path):
    db = tmp_path / "state.db"
    _, root_fingerprint, admission = _persist_root(db)

    connection = sqlite3.connect(db)
    connection.execute(
        """
        UPDATE recursive_work_state
        SET ancestry_json = '[]'
        WHERE lineage_id = ? AND work_fingerprint = ?
        """,
        ("atomic-lineage", root_fingerprint),
    )
    connection.commit()
    connection.close()

    store = SqliteRecursiveAdmissionStore(db)
    with pytest.raises(ValueError, match="digest mismatch"):
        store.commit_child(
            parent_work_fingerprint=root_fingerprint,
            parent_budget_before=_root_budget(),
            expected_parent_budget_generation=1,
            admission=admission,
        )
    store.close()

    budgets = SqliteBudgetStore(db)
    parent_budget, parent_generation = budgets.get("atomic-lineage", "root")
    assert parent_budget == _root_budget()
    assert parent_generation == 1
    budgets.close()
