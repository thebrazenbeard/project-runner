import sqlite3
from pathlib import Path

import pytest

from runner.budgets import BudgetEnvelope
from runner.persistent_state import SqliteBudgetStore, SqliteLeaseStore


def _budget():
    return BudgetEnvelope(
        lineage_id="lineage-1",
        max_depth=4,
        depth=1,
        remaining_children=5,
        remaining_active=3,
        remaining_retries=2,
        remaining_backend_jobs=4,
    )


def test_budget_store_survives_reopen_and_uses_generation_cas(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SqliteBudgetStore(db)
    generation = store.put_initial(_budget())
    assert generation == 1
    store.close()

    reopened = SqliteBudgetStore(db)
    loaded, loaded_generation = reopened.get("lineage-1")
    assert loaded == _budget()
    assert loaded_generation == 1

    updated = BudgetEnvelope(
        lineage_id="lineage-1",
        max_depth=4,
        depth=1,
        remaining_children=4,
        remaining_active=2,
        remaining_retries=2,
        remaining_backend_jobs=3,
    )
    assert reopened.compare_and_swap(updated, expected_generation=1) == 2
    with pytest.raises(ValueError, match="generation"):
        reopened.compare_and_swap(_budget(), expected_generation=1)
    reopened.close()


def test_sqlite_lease_reclaim_increments_fence_after_restart(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SqliteLeaseStore(db)
    first = store.claim("fp-1", holder="a", now=100.0, ttl=10.0)
    assert first is not None
    assert first.fencing_token == 1
    store.close()

    reopened = SqliteLeaseStore(db)
    second = reopened.claim("fp-1", holder="b", now=111.0, ttl=10.0)
    assert second is not None
    assert second.fencing_token == 2
    assert reopened.complete(first, now=112.0) is False
    assert reopened.complete(second, now=112.0) is True
    reopened.close()


def test_sqlite_lease_nonexpired_claim_is_atomic(tmp_path: Path):
    db = tmp_path / "state.db"
    a = SqliteLeaseStore(db)
    b = SqliteLeaseStore(db)

    first = a.claim("fp-1", holder="a", now=100.0, ttl=30.0)
    second = b.claim("fp-1", holder="b", now=101.0, ttl=30.0)

    assert first is not None
    assert second is None

    a.close()
    b.close()
