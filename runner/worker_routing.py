from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import (
    Frontier,
    InvocationRoute,
    ProjectDefinition,
    ReplayPolicy,
    RouteEffectClass,
    RouteState,
    WorkerDefinition,
    WorkerLifecycle,
)


@dataclass(frozen=True)
class ReadOnlyWorkerRoute:
    worker_id: str
    invocation_route: InvocationRoute
    replay_policy: ReplayPolicy


@dataclass(frozen=True)
class WorkerRouteEnvelope:
    route_id: str
    snapshot_id: int
    frontier_fingerprint: str
    queue_fencing_token: int
    worker_registry_digest: str
    worker_id: str
    invocation_route: InvocationRoute
    replay_policy: ReplayPolicy
    state: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS worker_route_outbox (
    route_id TEXT PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    frontier_fingerprint TEXT NOT NULL,
    queue_fencing_token INTEGER NOT NULL,
    worker_registry_digest TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    invocation_route TEXT NOT NULL,
    replay_policy TEXT NOT NULL,
    target_repository TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    target_head TEXT NOT NULL,
    frontier_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(snapshot_id, frontier_fingerprint, queue_fencing_token)
);
"""


def resolve_read_only_worker_route(
    *,
    project: ProjectDefinition,
    frontier: Frontier,
    workers: Iterable[WorkerDefinition],
) -> ReadOnlyWorkerRoute | None:
    target = next(
        (
            item
            for item in project.execution_targets
            if item.work_type == frontier.work_type
        ),
        None,
    )
    if target is None:
        raise ValueError("frontier lacks an explicit execution target")
    if target.worker_id is None or target.worker_route is None:
        if frontier.work_type == "INSPECT":
            return None
        raise ValueError(
            "non-INSPECT read-only work requires an explicit worker route"
        )

    matches = tuple(worker for worker in workers if worker.id == target.worker_id)
    if len(matches) != 1:
        raise ValueError("execution target worker is absent or ambiguous")
    worker = matches[0]
    if worker.lifecycle is not WorkerLifecycle.EXECUTABLE:
        raise ValueError("execution target worker is not EXECUTABLE")
    if worker.routes.get(target.worker_route) is not RouteState.VERIFIED:
        raise ValueError("execution target worker route is not VERIFIED")
    contract = worker.route_contracts.get(target.worker_route)
    if contract is None:
        raise ValueError("execution target worker route lacks an effect contract")
    if contract.effect_class is not RouteEffectClass.READ_ONLY:
        raise ValueError("worker route is not qualified as READ_ONLY")

    return ReadOnlyWorkerRoute(
        worker_id=worker.id,
        invocation_route=target.worker_route,
        replay_policy=contract.replay_policy,
    )


def worker_route_ready(
    *,
    project: ProjectDefinition,
    frontier: Frontier,
    workers: Iterable[WorkerDefinition],
) -> bool:
    try:
        route = resolve_read_only_worker_route(
            project=project,
            frontier=frontier,
            workers=workers,
        )
    except ValueError:
        return False
    return frontier.work_type == "INSPECT" or route is not None


def _route_payload(
    *,
    snapshot_id: int,
    frontier_fingerprint: str,
    queue_fencing_token: int,
    worker_registry_digest: str,
    route: ReadOnlyWorkerRoute,
    target_repository: str,
    target_ref: str,
    target_head: str,
    frontier_json: str,
) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "frontier_fingerprint": frontier_fingerprint,
        "queue_fencing_token": queue_fencing_token,
        "worker_registry_digest": worker_registry_digest,
        "worker_id": route.worker_id,
        "invocation_route": route.invocation_route.value,
        "replay_policy": route.replay_policy.value,
        "target_repository": target_repository,
        "target_ref": target_ref,
        "target_head": target_head,
        "frontier_json": json.loads(frontier_json),
    }


class SqliteWorkerRouteStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def enqueue(
        self,
        *,
        snapshot_id: int,
        frontier_fingerprint: str,
        queue_fencing_token: int,
        worker_registry_digest: str,
        route: ReadOnlyWorkerRoute,
        target_repository: str,
        target_ref: str,
        target_head: str,
        frontier_json: str,
        now: float,
    ) -> WorkerRouteEnvelope:
        payload = _route_payload(
            snapshot_id=snapshot_id,
            frontier_fingerprint=frontier_fingerprint,
            queue_fencing_token=queue_fencing_token,
            worker_registry_digest=worker_registry_digest,
            route=route,
            target_repository=target_repository,
            target_ref=target_ref,
            target_head=target_head,
            frontier_json=frontier_json,
        )
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        route_id = f"worker-route-{digest[:24]}"

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                """
                SELECT route_id, payload_sha256, state
                FROM worker_route_outbox
                WHERE snapshot_id = ?
                  AND frontier_fingerprint = ?
                  AND queue_fencing_token = ?
                """,
                (
                    snapshot_id,
                    frontier_fingerprint,
                    queue_fencing_token,
                ),
            ).fetchone()
            if existing is not None:
                if str(existing[1]) != digest:
                    raise ValueError(
                        "worker route identity already exists with different payload"
                    )
                self.connection.commit()
                return WorkerRouteEnvelope(
                    route_id=str(existing[0]),
                    snapshot_id=snapshot_id,
                    frontier_fingerprint=frontier_fingerprint,
                    queue_fencing_token=queue_fencing_token,
                    worker_registry_digest=worker_registry_digest,
                    worker_id=route.worker_id,
                    invocation_route=route.invocation_route,
                    replay_policy=route.replay_policy,
                    state=str(existing[2]),
                )

            self.connection.execute(
                """
                INSERT INTO worker_route_outbox(
                    route_id, snapshot_id, frontier_fingerprint,
                    queue_fencing_token, worker_registry_digest,
                    worker_id, invocation_route, replay_policy,
                    target_repository, target_ref, target_head,
                    frontier_json, payload_sha256, state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    route_id,
                    snapshot_id,
                    frontier_fingerprint,
                    queue_fencing_token,
                    worker_registry_digest,
                    route.worker_id,
                    route.invocation_route.value,
                    route.replay_policy.value,
                    target_repository,
                    target_ref,
                    target_head,
                    frontier_json,
                    digest,
                    now,
                    now,
                ),
            )
            self.connection.commit()
            return WorkerRouteEnvelope(
                route_id=route_id,
                snapshot_id=snapshot_id,
                frontier_fingerprint=frontier_fingerprint,
                queue_fencing_token=queue_fencing_token,
                worker_registry_digest=worker_registry_digest,
                worker_id=route.worker_id,
                invocation_route=route.invocation_route,
                replay_policy=route.replay_policy,
                state="PENDING",
            )
        except BaseException:
            self.connection.rollback()
            raise

    def summary(self) -> dict[str, object]:
        rows = self.connection.execute(
            """
            SELECT state, COUNT(*)
            FROM worker_route_outbox
            GROUP BY state
            ORDER BY state
            """
        ).fetchall()
        states = {str(state): int(count) for state, count in rows}
        return {"routes": sum(states.values()), "states": states}


def summarize_worker_routes(state_db: Path) -> dict[str, object]:
    state_db = Path(state_db)
    if not state_db.exists():
        return {"routes": 0, "states": {}}
    store = SqliteWorkerRouteStore(state_db)
    try:
        return store.summary()
    finally:
        store.close()
