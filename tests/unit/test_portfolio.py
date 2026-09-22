from pathlib import Path

import pytest

from runner.models import DependencyEdge, ProjectDefinition
from runner.portfolio import (
    SqlitePortfolioStore,
    collect_and_schedule_portfolio,
    summarize_portfolio_state,
)


class FakeTransport:
    def __init__(self, heads):
        self.heads = dict(heads)
        self.calls = []

    def read_ref(self, repository: str, ref: str) -> str:
        self.calls.append((repository, ref))
        value = self.heads[(repository, ref)]
        if isinstance(value, Exception):
            raise value
        return value

    def read_file(self, repository: str, path: str, ref: str):
        raise AssertionError("portfolio V1 does not read files")

    def create_branch(self, repository: str, branch: str, sha: str) -> None:
        raise AssertionError("portfolio V1 is read-only")

    def put_file(
        self,
        repository: str,
        path: str,
        branch: str,
        content: str,
        message: str,
        expected_blob_sha: str | None = None,
    ) -> str:
        raise AssertionError("portfolio V1 is read-only")


def _project(
    project_id: str,
    repository: str,
    *,
    scheduling_state: str = "SCHEDULABLE",
) -> ProjectDefinition:
    return ProjectDefinition.from_mapping(
        {
            "id": project_id,
            "name": project_id,
            "visibility": "public",
            "repositories": [repository],
            "capabilities": ["read", "analyze"],
            "assignment_scope": "NONE",
            "review_scope": "NONE",
            "family_id": project_id,
            "scheduling_state": scheduling_state,
        }
    )


def _dependency(
    *,
    repository: str = "example/provider",
    ref: str = "main",
    path_prefix: str | None = "src/",
) -> DependencyEdge:
    selector = {"repository": repository, "ref": ref}
    if path_prefix is not None:
        selector["path_prefix"] = path_prefix
    return DependencyEdge.from_mapping(
        {
            "id": "provider-to-consumer",
            "provider": "provider",
            "consumer": "consumer",
            "kind": "source",
            "selector": selector,
            "reaction": "INSPECT",
            "evidence": "exact-subject",
        }
    )


def _run(
    db: Path,
    transport: FakeTransport,
    *,
    consumer_state: str = "SCHEDULABLE",
    registry_digest: str = "1" * 64,
    dependency_digest: str = "2" * 64,
):
    return collect_and_schedule_portfolio(
        projects=(
            _project("provider", "example/provider"),
            _project(
                "consumer",
                "example/consumer",
                scheduling_state=consumer_state,
            ),
        ),
        dependencies=(_dependency(),),
        registry_digest=registry_digest,
        dependency_digest=dependency_digest,
        state_db=db,
        token=None,
        transport=transport,
        clock=lambda: 100.0,
    )


def test_first_cycle_is_baseline_and_second_change_queues_ready_frontier(
    tmp_path: Path,
):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("example/provider", "main"): "a" * 40}
    )

    baseline = _run(db, transport)
    assert baseline.baseline is True
    assert baseline.observation_count == 1
    assert baseline.changed_count == 0
    assert baseline.frontier_count == 0
    assert baseline.queued_count == 0

    transport.heads[("example/provider", "main")] = "b" * 40
    changed = _run(db, transport)

    assert changed.baseline is False
    assert changed.changed_count == 1
    assert changed.frontier_count == 1
    assert changed.ready_count == 1
    assert changed.blocked_count == 0
    assert changed.queued_count == 1

    summary = summarize_portfolio_state(db)
    assert summary["snapshots"] == 2
    assert summary["ready"] == 1
    assert summary["queued_total"] == 1

    store = SqlitePortfolioStore(db)
    try:
        row = store.connection.execute(
            """
            SELECT status, queue_state, subject_commit, subject_path
            FROM portfolio_frontiers
            WHERE snapshot_id = ?
            """,
            (changed.snapshot_id,),
        ).fetchone()
    finally:
        store.close()

    assert row == ("READY", "QUEUED", "b" * 40, "src/")


def test_no_change_creates_snapshot_without_duplicate_work(tmp_path: Path):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("example/provider", "main"): "a" * 40}
    )

    _run(db, transport)
    unchanged = _run(db, transport)

    assert unchanged.baseline is False
    assert unchanged.changed_count == 0
    assert unchanged.frontier_count == 0
    assert unchanged.queued_count == 0


def test_held_consumer_is_persisted_blocked_not_queued(tmp_path: Path):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("example/provider", "main"): "a" * 40}
    )

    _run(db, transport, consumer_state="HELD")
    transport.heads[("example/provider", "main")] = "b" * 40
    result = _run(db, transport, consumer_state="HELD")

    assert result.frontier_count == 1
    assert result.ready_count == 0
    assert result.blocked_count == 1
    assert result.queued_count == 0

    store = SqlitePortfolioStore(db)
    try:
        row = store.connection.execute(
            """
            SELECT status, queue_state
            FROM portfolio_frontiers
            WHERE snapshot_id = ?
            """,
            (result.snapshot_id,),
        ).fetchone()
    finally:
        store.close()

    assert row == ("WAITING_SCHEDULING", "BLOCKED")


def test_dependency_provider_scope_is_validated_before_transport_or_state(
    tmp_path: Path,
):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("attacker/repository", "main"): "a" * 40}
    )

    with pytest.raises(
        ValueError,
        match="outside its provider project scope",
    ):
        collect_and_schedule_portfolio(
            projects=(
                _project("provider", "example/provider"),
                _project("consumer", "example/consumer"),
            ),
            dependencies=(
                _dependency(repository="attacker/repository"),
            ),
            registry_digest="1" * 64,
            dependency_digest="2" * 64,
            state_db=db,
            token=None,
            transport=transport,
        )

    assert transport.calls == []
    assert not db.exists()


def test_transport_failure_does_not_advance_durable_snapshot(tmp_path: Path):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("example/provider", "main"): "a" * 40}
    )
    first = _run(db, transport)

    transport.heads[("example/provider", "main")] = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _run(db, transport)

    summary = summarize_portfolio_state(db)
    assert summary["snapshots"] == 1
    assert summary["latest_snapshot_id"] == first.snapshot_id


def test_dependency_digest_change_establishes_new_baseline(tmp_path: Path):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport(
        {("example/provider", "main"): "a" * 40}
    )

    _run(db, transport, dependency_digest="2" * 64)
    transport.heads[("example/provider", "main")] = "b" * 40

    reset = _run(db, transport, dependency_digest="3" * 64)
    assert reset.baseline is True
    assert reset.changed_count == 0
    assert reset.frontier_count == 0
    assert reset.queued_count == 0


def test_exact_ref_is_required_for_currentness_collection(tmp_path: Path):
    db = tmp_path / "portfolio.sqlite3"
    transport = FakeTransport({})

    with pytest.raises(
        ValueError,
        match="requires an exact dependency ref",
    ):
        collect_and_schedule_portfolio(
            projects=(
                _project("provider", "example/provider"),
                _project("consumer", "example/consumer"),
            ),
            dependencies=(
                _dependency(ref=""),
            ),
            registry_digest="1" * 64,
            dependency_digest="2" * 64,
            state_db=db,
            token=None,
            transport=transport,
        )

    assert transport.calls == []
    assert not db.exists()
