from pathlib import Path

import pytest

from runner.models import Frontier, ProjectDefinition, WorkerDefinition
from runner.worker_routing import (
    SqliteWorkerRouteStore,
    resolve_read_only_worker_route,
)


def _project(*, worker=True):
    target = {
        "work_type": "REREVIEW",
        "repository": "example/consumer",
        "ref": "main",
    }
    if worker:
        target.update(
            {
                "worker_id": "reviewer",
                "worker_route": "OPENAI_AGENT_API",
            }
        )
    return ProjectDefinition.from_mapping(
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
            "execution_targets": [target],
        }
    )


def _worker(
    *,
    route_state: str = "VERIFIED",
    effect_class: str = "READ_ONLY",
    replay_policy: str = "SAFE",
):
    return WorkerDefinition.from_mapping(
        {
            "id": "reviewer",
            "name": "Reviewer",
            "worker_type": "OPENAI_AGENT",
            "lifecycle": "EXECUTABLE",
            "locators": {"model": "reviewer-model"},
            "roles": ["review"],
            "routes": {"OPENAI_AGENT_API": route_state},
            "route_contracts": {
                "OPENAI_AGENT_API": {
                    "effect_class": effect_class,
                    "replay_policy": replay_policy,
                }
            },
            "reconstruction": {
                "repository": "example/worker-definitions",
                "path": "workers/reviewer.md",
                "commit": "a" * 40,
            },
        }
    )


def _frontier():
    return Frontier.from_mapping(
        {
            "id": "frontier-review",
            "project": "consumer",
            "subject": {
                "repository": "example/provider",
                "ref": "main",
                "commit": "b" * 40,
            },
            "work_type": "REREVIEW",
            "reason": "provider changed",
            "dependencies": ["provider-consumer"],
            "required_capabilities": ["analyze"],
            "collision_keys": ["project:consumer"],
            "cost_class": "SMALL",
            "priority_inputs": {
                "fanout": 1,
                "blocked_downstream": 0,
                "staleness_risk": 1,
                "failure_severity": 0,
                "declared_priority": 0,
                "cost": 1,
                "authority_available": 1,
                "scheduling_eligible": 1,
                "executable_now": 1,
            },
            "status": "READY",
        }
    )


def test_verified_read_only_worker_route_resolves():
    route = resolve_read_only_worker_route(
        project=_project(),
        frontier=_frontier(),
        workers=(_worker(),),
    )
    assert route is not None
    assert route.worker_id == "reviewer"
    assert route.invocation_route.value == "OPENAI_AGENT_API"
    assert route.replay_policy.value == "SAFE"


def test_unverified_worker_route_is_rejected():
    with pytest.raises(ValueError, match="not VERIFIED"):
        resolve_read_only_worker_route(
            project=_project(),
            frontier=_frontier(),
            workers=(_worker(route_state="CONNECTED"),),
        )


def test_mutating_worker_route_is_rejected():
    with pytest.raises(ValueError, match="not qualified as READ_ONLY"):
        resolve_read_only_worker_route(
            project=_project(),
            frontier=_frontier(),
            workers=(_worker(effect_class="MUTATING"),),
        )


def test_non_inspect_work_requires_explicit_worker_binding():
    with pytest.raises(ValueError, match="requires an explicit worker route"):
        resolve_read_only_worker_route(
            project=_project(worker=False),
            frontier=_frontier(),
            workers=(_worker(),),
        )


def test_worker_route_outbox_is_idempotent_for_exact_queue_fence(tmp_path: Path):
    db = tmp_path / "worker-route.sqlite3"
    store = SqliteWorkerRouteStore(db)
    route = resolve_read_only_worker_route(
        project=_project(),
        frontier=_frontier(),
        workers=(_worker(),),
    )
    assert route is not None
    frontier_json = """{"id":"frontier-review"}"""

    first = store.enqueue(
        snapshot_id=2,
        frontier_fingerprint="f" * 64,
        queue_fencing_token=3,
        worker_registry_digest="1" * 64,
        route=route,
        target_repository="example/consumer",
        target_ref="main",
        target_head="c" * 40,
        frontier_json=frontier_json,
        now=10.0,
    )
    second = store.enqueue(
        snapshot_id=2,
        frontier_fingerprint="f" * 64,
        queue_fencing_token=3,
        worker_registry_digest="1" * 64,
        route=route,
        target_repository="example/consumer",
        target_ref="main",
        target_head="c" * 40,
        frontier_json=frontier_json,
        now=11.0,
    )
    store.close()

    assert first.route_id == second.route_id
    assert second.state == "PENDING"
