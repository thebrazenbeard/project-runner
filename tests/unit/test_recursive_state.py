from pathlib import Path

import pytest

from runner.budgets import BudgetEnvelope
from runner.decompose import admit_child_work
from runner.models import ExactSubject
from runner.recursive_state import SqliteRecursiveWorkStore
from runner.work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def _subject(commit: str) -> ExactSubject:
    return ExactSubject(
        repository="thebrazenbeard/project-runner",
        ref="work/public-safe-portfolio-registry-v2",
        commit=commit,
        path="runner/recursive_state.py",
    )


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
        root_frontier_id="frontier-recursive",
        parent_work_id=parent,
        inputs=(_subject(commit),),
        operation=operation,
        required_capabilities=("read", "analyze"),
        collision_keys=("project:project-runner",),
        recursion_depth=depth,
        budget_allocation={
            "children": 2,
            "active": 1,
            "retries": 1,
            "backend_jobs": 1,
        },
        expected_outputs=("verified-work",),
        completion_criteria=("exact-subject-current",),
        status=WorkUnitStatus.PENDING,
        payload={"mode": "recursive-state-test"},
    )


def _budget() -> BudgetEnvelope:
    return BudgetEnvelope(
        lineage_id="lineage-recursive",
        max_depth=3,
        depth=0,
        remaining_children=3,
        remaining_active=3,
        remaining_retries=2,
        remaining_backend_jobs=3,
    )


def _admit(parent: WorkUnit, child: WorkUnit, *, budget: BudgetEnvelope, ancestry=()):
    return admit_child_work(
        parent=parent,
        child=child,
        parent_budget=budget,
        parent_capabilities={"read", "analyze"},
        target_capabilities={"read", "analyze"},
        ancestry_fingerprints=ancestry,
        child_children=2,
        child_active=1,
        child_retries=1,
        child_backend_jobs=1,
    )


def test_recursive_work_survives_restart_with_parent_ancestry_and_scope(tmp_path: Path):
    db = tmp_path / "recursive.db"
    root = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    root_fingerprint = work_unit_fingerprint(root)

    store = SqliteRecursiveWorkStore(db)
    stored_root = store.put_initial(
        work=root,
        lineage_id="lineage-recursive",
        budget_scope_id="root",
        parent_fingerprint=None,
        ancestry_fingerprints={root_fingerprint},
    )

    child = _work(
        "child",
        depth=1,
        parent=root.id,
        commit="b" * 40,
        operation="REREVIEW",
    )
    admitted = _admit(root, child, budget=_budget())
    child_fingerprint = work_unit_fingerprint(admitted.work)

    stored_child = store.put_initial(
        work=admitted.work,
        lineage_id="lineage-recursive",
        budget_scope_id=admitted.child_budget.scope_id,
        parent_fingerprint=root_fingerprint,
        ancestry_fingerprints=admitted.ancestry_fingerprints,
    )
    assert stored_root.generation == stored_child.generation == 1
    store.close()

    reopened = SqliteRecursiveWorkStore(db)
    resumed = reopened.get("lineage-recursive", child_fingerprint)
    assert resumed is not None
    assert resumed.work == admitted.work
    assert resumed.parent_fingerprint == root_fingerprint
    assert resumed.ancestry_fingerprints == admitted.ancestry_fingerprints
    assert resumed.budget_scope_id == "work:" + child_fingerprint
    reopened.close()


def test_recursive_work_status_cas_is_scope_local_and_stale_generation_fails(
    tmp_path: Path,
):
    db = tmp_path / "recursive.db"
    root = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    fingerprint = work_unit_fingerprint(root)

    store = SqliteRecursiveWorkStore(db)
    store.put_initial(
        work=root,
        lineage_id="lineage-recursive",
        budget_scope_id="root",
        parent_fingerprint=None,
        ancestry_fingerprints={fingerprint},
    )

    running = store.compare_and_swap_status(
        lineage_id="lineage-recursive",
        work_fingerprint_value=fingerprint,
        expected_generation=1,
        status=WorkUnitStatus.RUNNING,
    )
    assert running.generation == 2
    assert running.work.status is WorkUnitStatus.RUNNING

    with pytest.raises(ValueError, match="generation"):
        store.compare_and_swap_status(
            lineage_id="lineage-recursive",
            work_fingerprint_value=fingerprint,
            expected_generation=1,
            status=WorkUnitStatus.COMPLETE,
        )
    store.close()


def test_recursive_work_rejects_child_until_parent_is_durable(tmp_path: Path):
    store = SqliteRecursiveWorkStore(tmp_path / "recursive.db")
    parent = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    child = _work(
        "child",
        depth=1,
        parent=parent.id,
        commit="b" * 40,
        operation="REREVIEW",
    )
    admitted = _admit(parent, child, budget=_budget())

    with pytest.raises(ValueError, match="parent is not durable"):
        store.put_initial(
            work=admitted.work,
            lineage_id="lineage-recursive",
            budget_scope_id=admitted.child_budget.scope_id,
            parent_fingerprint=work_unit_fingerprint(parent),
            ancestry_fingerprints=admitted.ancestry_fingerprints,
        )
    store.close()


def test_recursive_work_detects_immutable_state_tampering(tmp_path: Path):
    db = tmp_path / "recursive.db"
    root = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    fingerprint = work_unit_fingerprint(root)
    store = SqliteRecursiveWorkStore(db)
    store.put_initial(
        work=root,
        lineage_id="lineage-recursive",
        budget_scope_id="root",
        parent_fingerprint=None,
        ancestry_fingerprints={fingerprint},
    )

    store.connection.execute(
        """
        UPDATE recursive_work_state
        SET ancestry_json = '[]'
        WHERE lineage_id = ? AND work_fingerprint = ?
        """,
        ("lineage-recursive", fingerprint),
    )

    with pytest.raises(ValueError, match="digest mismatch"):
        store.get("lineage-recursive", fingerprint)
    store.close()


def test_post_restart_ancestry_still_rejects_a_to_b_to_a_cycle(tmp_path: Path):
    db = tmp_path / "recursive.db"
    root = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    root_fingerprint = work_unit_fingerprint(root)

    store = SqliteRecursiveWorkStore(db)
    store.put_initial(
        work=root,
        lineage_id="lineage-recursive",
        budget_scope_id="root",
        parent_fingerprint=None,
        ancestry_fingerprints={root_fingerprint},
    )

    child = _work(
        "child",
        depth=1,
        parent=root.id,
        commit="b" * 40,
        operation="REREVIEW",
    )
    admitted_child = _admit(root, child, budget=_budget())
    child_fingerprint = work_unit_fingerprint(admitted_child.work)
    store.put_initial(
        work=admitted_child.work,
        lineage_id="lineage-recursive",
        budget_scope_id=admitted_child.child_budget.scope_id,
        parent_fingerprint=root_fingerprint,
        ancestry_fingerprints=admitted_child.ancestry_fingerprints,
    )
    store.close()

    reopened = SqliteRecursiveWorkStore(db)
    resumed_child = reopened.get("lineage-recursive", child_fingerprint)
    assert resumed_child is not None

    root_again = _work(
        "root-renamed",
        depth=2,
        parent=child.id,
        commit="a" * 40,
        operation="INSPECT",
    )
    with pytest.raises(ValueError, match="cycle"):
        admit_child_work(
            parent=resumed_child.work,
            child=root_again,
            parent_budget=admitted_child.child_budget,
            parent_capabilities={"read", "analyze"},
            target_capabilities={"read", "analyze"},
            ancestry_fingerprints=resumed_child.ancestry_fingerprints,
            child_children=0,
            child_active=0,
            child_retries=0,
            child_backend_jobs=0,
        )
    reopened.close()


def test_same_semantic_work_isolated_between_lineages(tmp_path: Path):
    db = tmp_path / "recursive.db"
    work = _work(
        "root",
        depth=0,
        parent=None,
        commit="a" * 40,
        operation="INSPECT",
    )
    fingerprint = work_unit_fingerprint(work)
    store = SqliteRecursiveWorkStore(db)

    for lineage_id in ("lineage-a", "lineage-b"):
        stored = store.put_initial(
            work=work,
            lineage_id=lineage_id,
            budget_scope_id="root",
            parent_fingerprint=None,
            ancestry_fingerprints={fingerprint},
        )
        assert stored.lineage_id == lineage_id

    with pytest.raises(ValueError, match="already exists"):
        store.put_initial(
            work=work,
            lineage_id="lineage-a",
            budget_scope_id="root",
            parent_fingerprint=None,
            ancestry_fingerprints={fingerprint},
        )
    store.close()
