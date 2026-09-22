from pathlib import Path

from runner.budgets import BudgetEnvelope
from runner.durable_dispatch import SqliteDispatchAdmissionStore
from runner.m6_github import frontier_to_github_inspection_work
from runner.models import DependencyEdge, ExactSubject, ProjectDefinition
from runner.portfolio import collect_and_schedule_portfolio
from runner.queue_consumer import (
    SqliteQueueStore,
    consume_next_queued_inspection,
    summarize_queue_state,
)


class FakeTransport:
    def __init__(self, heads):
        self.heads = dict(heads)
        self.calls = []

    def read_ref(self, repository: str, ref: str) -> str:
        self.calls.append((repository, ref))
        return self.heads[(repository, ref)]

    def read_file(self, repository: str, path: str, ref: str):
        raise AssertionError("queue bridge is ref-read only")

    def create_branch(self, repository: str, branch: str, sha: str) -> None:
        raise AssertionError("queue bridge is read-only")

    def put_file(
        self,
        repository: str,
        path: str,
        branch: str,
        content: str,
        message: str,
        expected_blob_sha: str | None = None,
    ) -> str:
        raise AssertionError("queue bridge is read-only")


def _projects(*, target_ref: str = "main"):
    provider = ProjectDefinition.from_mapping(
        {
            "id": "provider",
            "name": "Provider",
            "visibility": "public",
            "repositories": ["example/provider"],
            "capabilities": ["read", "analyze"],
            "assignment_scope": "NONE",
            "review_scope": "NONE",
            "family_id": "provider",
            "scheduling_state": "SCHEDULABLE",
        }
    )
    consumer = ProjectDefinition.from_mapping(
        {
            "id": "consumer",
            "name": "Consumer",
            "visibility": "public",
            "repositories": ["example/consumer"],
            "capabilities": ["read", "analyze"],
            "assignment_scope": "NONE",
            "review_scope": "NONE",
            "family_id": "consumer",
            "scheduling_state": "SCHEDULABLE",
            "execution_targets": [
                {
                    "work_type": "INSPECT",
                    "repository": "example/consumer",
                    "ref": target_ref,
                }
            ],
        }
    )
    return provider, consumer


def _dependency():
    return DependencyEdge.from_mapping(
        {
            "id": "provider-to-consumer",
            "provider": "provider",
            "consumer": "consumer",
            "kind": "source",
            "selector": {
                "repository": "example/provider",
                "ref": "main",
            },
            "reaction": "INSPECT",
            "evidence": "exact-subject",
        }
    )


def _schedule(
    db: Path,
    transport: FakeTransport,
    *,
    registry_digest: str = "1" * 64,
    dependency_digest: str = "2" * 64,
    target_ref: str = "main",
):
    projects = _projects(target_ref=target_ref)
    dependency = (_dependency(),)
    collect_and_schedule_portfolio(
        projects=projects,
        dependencies=dependency,
        registry_digest=registry_digest,
        dependency_digest=dependency_digest,
        state_db=db,
        token=None,
        transport=transport,
        clock=lambda: 1.0,
    )
    transport.heads[("example/provider", "main")] = "b" * 40
    changed = collect_and_schedule_portfolio(
        projects=projects,
        dependencies=dependency,
        registry_digest=registry_digest,
        dependency_digest=dependency_digest,
        state_db=db,
        token=None,
        transport=transport,
        clock=lambda: 2.0,
    )
    assert changed.queued_count == 1
    return projects, changed


def test_queue_consumer_executes_declared_target_and_completes(tmp_path: Path):
    db = tmp_path / "queue.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "main"): "c" * 40,
        }
    )
    projects, changed = _schedule(db, transport)
    transport.calls.clear()

    result = consume_next_queued_inspection(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        holder="queue-test",
        lease_ttl=60.0,
        token=None,
        transport=transport,
        clock=lambda: 3.0,
    )

    assert result.claimed is True
    assert result.queue_state == "COMPLETE"
    assert result.snapshot_id == changed.snapshot_id
    assert result.fencing_token == 1
    assert result.operator_status == "COMPLETE"
    assert transport.calls == [
        ("example/consumer", "main"),
        ("example/provider", "main"),
        ("example/consumer", "main"),
        ("example/provider", "main"),
        ("example/consumer", "main"),
    ]
    assert summarize_queue_state(db) == {
        "claims": 1,
        "states": {"COMPLETE": 1},
    }


def test_queue_consumer_uses_declared_nondefault_ref(tmp_path: Path):
    db = tmp_path / "queue-target-ref.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "review"): "c" * 40,
        }
    )
    projects, _changed = _schedule(
        db,
        transport,
        target_ref="review",
    )
    transport.calls.clear()

    result = consume_next_queued_inspection(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        holder="queue-test",
        lease_ttl=60.0,
        token=None,
        transport=transport,
        clock=lambda: 3.0,
    )

    assert result.queue_state == "COMPLETE"
    assert ("example/consumer", "review") in transport.calls
    assert ("example/consumer", "main") not in transport.calls


def test_queue_claim_is_fenced_and_reclaim_increments_token(tmp_path: Path):
    db = tmp_path / "queue-fence.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "main"): "c" * 40,
        }
    )
    projects, _changed = _schedule(db, transport)

    store = SqliteQueueStore(db)
    try:
        first = store.claim_next(
            projects=projects,
            registry_digest="1" * 64,
            dependency_digest="2" * 64,
            holder="one",
            now=3.0,
            ttl=10.0,
        )
        assert first is not None
        assert first.fencing_token == 1

        blocked = store.claim_next(
            projects=projects,
            registry_digest="1" * 64,
            dependency_digest="2" * 64,
            holder="two",
            now=4.0,
            ttl=10.0,
        )
        assert blocked is None

        reclaimed = store.claim_next(
            projects=projects,
            registry_digest="1" * 64,
            dependency_digest="2" * 64,
            holder="two",
            now=14.0,
            ttl=10.0,
        )
        assert reclaimed is not None
        assert reclaimed.frontier_fingerprint == first.frontier_fingerprint
        assert reclaimed.fencing_token == 2
    finally:
        store.close()


def test_newer_snapshot_without_queue_supersedes_old_queue_visibility(tmp_path: Path):
    db = tmp_path / "queue-current-snapshot.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "main"): "c" * 40,
        }
    )
    projects, _changed = _schedule(db, transport)
    collect_and_schedule_portfolio(
        projects=projects,
        dependencies=(_dependency(),),
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        token=None,
        transport=transport,
        clock=lambda: 3.0,
    )
    transport.calls.clear()

    result = consume_next_queued_inspection(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        holder="queue-test",
        lease_ttl=60.0,
        token=None,
        transport=transport,
        clock=lambda: 4.0,
    )

    assert result.claimed is False
    assert result.queue_state == "NO_WORK"
    assert transport.calls == []


def test_reclaimed_queue_reconciles_terminal_operator_without_reexecution(
    tmp_path: Path,
):
    db = tmp_path / "queue-reconcile.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "main"): "c" * 40,
        }
    )
    projects, _changed = _schedule(db, transport)

    store = SqliteQueueStore(db)
    claim = store.claim_next(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        holder="first-holder",
        now=3.0,
        ttl=5.0,
    )
    assert claim is not None
    claim = store.bind_target_head(
        claim,
        target_head="c" * 40,
        now=3.1,
    )
    store.close()

    from runner.operator import run_durable_github_read_inspection

    operator_result = run_durable_github_read_inspection(
        frontier=claim.frontier,
        target_subject=ExactSubject(
            repository=claim.target_repository,
            ref=claim.target_ref,
            commit=claim.target_head,
        ),
        state_db=db,
        lineage_id=claim.operator_lineage,
        holder="first-holder",
        lease_ttl=60.0,
        registry_digest="1" * 64,
        authorized_target_repositories=("example/consumer",),
        authorized_provider_repositories=("example/provider",),
        token=None,
        transport=transport,
        clock=lambda: 3.2,
    )
    assert operator_result.status is WorkUnitStatus.COMPLETE
    transport.calls.clear()

    recovered = consume_next_queued_inspection(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        holder="second-holder",
        lease_ttl=60.0,
        token=None,
        transport=transport,
        clock=lambda: 9.0,
    )

    assert recovered.queue_state == "COMPLETE"
    assert recovered.fencing_token == 2
    assert recovered.operator_status == "COMPLETE"
    assert transport.calls == []


def test_reclaimed_queue_refuses_nonterminal_operator_reexecution(tmp_path: Path):
    db = tmp_path / "queue-ambiguous.sqlite3"
    transport = FakeTransport(
        {
            ("example/provider", "main"): "a" * 40,
            ("example/consumer", "main"): "c" * 40,
        }
    )
    projects, _changed = _schedule(db, transport)

    store = SqliteQueueStore(db)
    claim = store.claim_next(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        holder="first-holder",
        now=3.0,
        ttl=5.0,
    )
    assert claim is not None
    claim = store.bind_target_head(
        claim,
        target_head="c" * 40,
        now=3.1,
    )
    store.close()

    work = frontier_to_github_inspection_work(
        claim.frontier,
        ExactSubject(
            repository=claim.target_repository,
            ref=claim.target_ref,
            commit=claim.target_head,
        ),
        registry_digest="1" * 64,
    )
    dispatch = SqliteDispatchAdmissionStore(db)
    dispatch.initialize_root(
        budget=BudgetEnvelope(
            lineage_id=claim.operator_lineage,
            max_depth=1,
            depth=0,
            remaining_children=0,
            remaining_active=2,
            remaining_retries=1,
            remaining_backend_jobs=2,
        ),
        work=work,
        effective_capabilities={"read", "analyze"},
    )
    dispatch.close()
    transport.calls.clear()

    recovered = consume_next_queued_inspection(
        projects=projects,
        registry_digest="1" * 64,
        dependency_digest="2" * 64,
        state_db=db,
        holder="second-holder",
        lease_ttl=60.0,
        token=None,
        transport=transport,
        clock=lambda: 9.0,
    )

    assert recovered.queue_state == "OUTCOME_UNKNOWN"
    assert recovered.operator_status == "PENDING"
    assert "re-execution was not attempted" in recovered.reason
    assert transport.calls == []
