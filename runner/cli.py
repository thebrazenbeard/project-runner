from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hmac
import json
import os
from pathlib import Path
import time
from typing import Sequence

from .backends import MockBackend
from .budgets import BudgetEnvelope
from .collisions import partition_collision_groups
from .currentness import observation_locus, subject_changed
from .dedup import deduplicate_frontiers, frontier_fingerprint
from .dispatch import dispatch_ready
from .frontier import derive_frontiers
from .github_backend import GitHubBackend, GitHubOperation, GitHubRestTransport, TargetAuthorityGrant
from .leases import InMemoryLeaseStore
from .models import ExactSubject, FrontierStatus, ProjectSchedulingState
from .operator import (
    build_github_read_backend,
    run_durable_github_read_inspection,
    summarize_recovery_state,
)
from .prioritize import rank_frontiers
from .propagate import derive_invalidations
from .registry import load_dependencies, load_observations, load_project_snapshot, load_workers
from .verify import verify_attempt
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


ROOT = Path(__file__).resolve().parents[1]


def _project_registry_path() -> Path:
    override = os.environ.get("PROJECT_RUNNER_PROJECT_REGISTRY")
    if override is None:
        return ROOT / "registry" / "projects.yaml"

    path = Path(override).expanduser()
    if not path.is_absolute():
        raise ValueError("external project registry requires an absolute path")

    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise ValueError("external project registry is unavailable") from None

    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise ValueError(
            "external project registry must be outside the Project Runner checkout"
        )
    if not resolved.is_file():
        raise ValueError("external project registry is unavailable")
    return resolved


def _external_project_registry_selected() -> bool:
    return os.environ.get("PROJECT_RUNNER_PROJECT_REGISTRY") is not None


def _external_project_registry_expected_sha256() -> str:
    expected = os.environ.get("PROJECT_RUNNER_PROJECT_REGISTRY_SHA256", "")
    if (
        len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise ValueError(
            "external project registry requires an expected lowercase SHA-256"
        )
    return expected


def _external_private_collision_key() -> str:
    key = os.environ.get("PROJECT_RUNNER_PRIVATE_COLLISION_KEY", "")
    if (
        len(key) != 64
        or any(character not in "0123456789abcdef" for character in key)
    ):
        raise ValueError(
            "external project registry requires a private collision key"
        )
    return key


def _load_project_registry_snapshot():
    external = _external_project_registry_selected()
    path = _project_registry_path()
    expected = (
        _external_project_registry_expected_sha256()
        if external
        else None
    )
    snapshot = load_project_snapshot(
        path,
        require_scope_metadata=external,
    )
    if expected is not None and not hmac.compare_digest(snapshot.sha256, expected):
        raise ValueError("external project registry digest mismatch")
    return snapshot


def _load_project_registry():
    return _load_project_registry_snapshot().projects


def _require_public_safe_reporting() -> None:
    if _external_project_registry_selected():
        raise ValueError(
            "detailed reports are disabled with an external project registry"
        )


def _load_all():
    projects = _load_project_registry()
    workers = load_workers(ROOT / "registry" / "workers.yaml")
    return projects, workers


def _validate() -> int:
    projects, workers = _load_all()
    print(f"Registries valid: {len(projects)} projects, {len(workers)} workers")
    return 0


def _inventory() -> int:
    projects, workers = _load_all()
    counts = Counter(worker.lifecycle.value for worker in workers)
    print(f"Projects: {len(projects)}")
    print(f"Workers: {len(workers)}")
    for lifecycle in sorted(counts):
        print(f"{lifecycle.title()}: {counts[lifecycle]}")
    return 0


def _subject_payload(subject) -> dict[str, str | None]:
    return {
        "repository": subject.repository,
        "ref": subject.ref,
        "commit": subject.commit,
        "path": subject.path,
        "digest": subject.digest,
    }


def _evaluate_change(before: Path, after: Path, dependencies: Path) -> int:
    _require_public_safe_reporting()
    previous = load_observations(before)
    current = load_observations(after)
    edges = load_dependencies(dependencies)

    previous_by_locus = {observation_locus(item): item for item in previous}
    changed = [
        item for item in current
        if subject_changed(previous_by_locus.get(observation_locus(item)), item)
    ]
    invalidations = derive_invalidations(previous, current, edges)

    payload = {
        "changed_subjects": [
            {"target": item.target, **_subject_payload(item.subject)}
            for item in sorted(
                changed,
                key=lambda item: (
                    item.target,
                    item.subject.repository,
                    item.subject.ref,
                    item.subject.path or "",
                    item.subject.commit or "",
                ),
            )
        ],
        "invalidations": [
            {
                "dependency_id": item.dependency_id,
                "provider": item.provider,
                "consumer": item.consumer,
                "reaction": item.reaction.value,
                "subject": _subject_payload(item.changed_subject),
            }
            for item in sorted(
                invalidations,
                key=lambda item: (
                    item.dependency_id,
                    item.consumer,
                    item.changed_subject.repository,
                    item.changed_subject.path or "",
                ),
            )
        ],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _frontier_payload(frontier) -> dict[str, object]:
    return {
        "id": frontier.id,
        "fingerprint": frontier_fingerprint(frontier),
        "project": frontier.project,
        "subject": _subject_payload(frontier.subject),
        "work_type": frontier.work_type,
        "reason": frontier.reason,
        "dependencies": list(frontier.dependencies),
        "required_capabilities": list(frontier.required_capabilities),
        "collision_keys": list(frontier.collision_keys),
        "cost_class": frontier.cost_class.value,
        "priority_inputs": dict(sorted(frontier.priority_inputs.items())),
        "status": frontier.status.value,
    }


def _private_collision_key(key: str, private_collision_key: str) -> str:
    digest = hmac.new(
        bytes.fromhex(private_collision_key),
        key.encode("utf-8"),
        digestmod="sha256",
    ).hexdigest()
    return f"private:{digest}"


def _derive_frontier_set(before: Path, after: Path, dependencies: Path):
    previous = load_observations(before)
    current = load_observations(after)
    edges = load_dependencies(dependencies)
    snapshot = _load_project_registry_snapshot()
    projects = snapshot.projects
    capability_lookup = {
        project.id: set(project.capabilities)
        for project in projects
    }
    scheduling_lookup = {
        project.id: project.scheduling_state.schedulable
        for project in projects
    }

    invalidations = derive_invalidations(previous, current, edges)
    derived = derive_frontiers(
        invalidations,
        capability_lookup=capability_lookup,
        scheduling_lookup=scheduling_lookup,
    )
    if _external_project_registry_selected():
        private_collision_key = _external_private_collision_key()
        derived = tuple(
            replace(
                frontier,
                collision_keys=tuple(
                    _private_collision_key(key, private_collision_key)
                    for key in frontier.collision_keys
                ),
            )
            for frontier in derived
        )
    return deduplicate_frontiers(derived)


def _frontier_summary(before: Path, after: Path, dependencies: Path) -> int:
    try:
        frontiers = _derive_frontier_set(before, after, dependencies)
    except Exception:
        if _external_project_registry_selected():
            raise ValueError(
                "external frontier summary is unavailable or structurally invalid"
            ) from None
        raise

    status_counts = Counter(frontier.status.value for frontier in frontiers)
    ready = status_counts.get(FrontierStatus.READY.value, 0)
    payload = {
        "total": len(frontiers),
        "ready": ready,
        "blocked": len(frontiers) - ready,
        "statuses": dict(sorted(status_counts.items())),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _frontier_report(before: Path, after: Path, dependencies: Path) -> int:
    _require_public_safe_reporting()
    frontiers = _derive_frontier_set(before, after, dependencies)
    ordered_frontiers = tuple(sorted(frontiers, key=frontier_fingerprint))
    collision_groups = partition_collision_groups(ordered_frontiers)
    ranked = rank_frontiers(ordered_frontiers)

    payload = {
        "frontiers": [_frontier_payload(item) for item in ordered_frontiers],
        "collision_groups": [
            [item.id for item in group]
            for group in collision_groups
        ],
        "ranked": [
            {
                "id": decision.frontier.id,
                "project": decision.frontier.project,
                "work_type": decision.frontier.work_type,
                "status": decision.frontier.status.value,
                "score": decision.score,
                "reasons": list(decision.reasons),
            }
            for decision in ranked
        ],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _dispatch_report(before: Path, after: Path, dependencies: Path) -> int:
    _require_public_safe_reporting()
    frontiers = _derive_frontier_set(before, after, dependencies)
    blocked = tuple(
        sorted(
            (
                frontier
                for frontier in frontiers
                if frontier.status is not FrontierStatus.READY
            ),
            key=frontier_fingerprint,
        )
    )

    budget = BudgetEnvelope(
        lineage_id="m4-cli-fixture",
        max_depth=3,
        depth=0,
        remaining_children=16,
        remaining_active=8,
        remaining_retries=4,
        remaining_backend_jobs=8,
    )
    store = InMemoryLeaseStore()
    backend = MockBackend()
    batch = dispatch_ready(
        frontiers,
        lease_store=store,
        backend=backend,
        budget=budget,
        holder="project-runner-m4-mock",
        now=0.0,
        lease_ttl=60.0,
    )

    attempts = []
    for attempt in batch.attempts:
        outcome = verify_attempt(
            attempt,
            lease_store=store,
            now=1.0,
            current_subject_reader=lambda subject: subject,
            evidence_verifier=lambda work, result: (
                result.succeeded and "mock-backend" in result.evidence
            ),
        )
        attempts.append(
            {
                "frontier_id": attempt.frontier.id,
                "project": attempt.frontier.project,
                "work_id": attempt.work.id,
                "work_fingerprint": work_unit_fingerprint(attempt.work),
                "fencing_token": attempt.lease.fencing_token,
                "backend_succeeded": attempt.result.succeeded,
                "verification_status": outcome.status.value,
                "verification_reason": outcome.reason,
            }
        )

    payload = {
        "mode": "M4_MOCK_NO_DOWNSTREAM_EFFECTS",
        "attempts": attempts,
        "blocked": [
            {
                "id": frontier.id,
                "project": frontier.project,
                "work_type": frontier.work_type,
                "status": frontier.status.value,
            }
            for frontier in blocked
        ],
        "remaining_budget": {
            "children": batch.remaining_budget.remaining_children,
            "active": batch.remaining_budget.remaining_active,
            "retries": batch.remaining_budget.remaining_retries,
            "backend_jobs": batch.remaining_budget.remaining_backend_jobs,
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return 0



def _github_read_smoke(repository: str, ref: str, expected_head: str | None) -> int:
    token = os.environ.get("PROJECT_RUNNER_GITHUB_TOKEN")
    backend = GitHubBackend(
        transport=GitHubRestTransport(token=token),
        route_capabilities={"github.read_ref"},
        grants=(
            TargetAuthorityGrant(
                repository=repository,
                operations=(GitHubOperation.READ_REF,),
                ref_prefixes=(ref,),
            ),
        ),
    )
    work = WorkUnit(
        id="github-read-smoke",
        root_frontier_id="github-read-smoke",
        parent_work_id=None,
        inputs=(),
        operation="GITHUB",
        required_capabilities=("read",),
        collision_keys=(f"repo:{repository}",),
        recursion_depth=0,
        budget_allocation={"active": 1, "backend_jobs": 1},
        expected_outputs=("github-ref",),
        completion_criteria=("readback",),
        status=WorkUnitStatus.PENDING,
        payload={
            "github": {
                "operation": "READ_REF",
                "repository": repository,
                "ref": ref,
                "expected_head": expected_head,
            }
        },
    )
    result = backend.execute(work)
    print(json.dumps({
        "classification": result.classification,
        "succeeded": result.succeeded,
        "outputs": list(result.outputs),
        "evidence": list(result.evidence),
    }, sort_keys=True))
    return 0 if result.succeeded else 1


def _select_ready_inspection(frontiers, *, project: str, frontier_id: str | None):
    candidates = tuple(
        frontier
        for frontier in frontiers
        if frontier.status is FrontierStatus.READY
        and frontier.work_type == "INSPECT"
        and frontier.project == project
        and (frontier_id is None or frontier.id == frontier_id)
    )
    if not candidates:
        raise ValueError("no matching READY INSPECT frontier")
    if len(candidates) != 1:
        raise ValueError(
            "multiple matching READY INSPECT frontiers; supply --frontier-id"
        )
    return candidates[0]


def _run_inspection(args) -> int:
    frontiers = _derive_frontier_set(
        args.before,
        args.after,
        args.dependencies,
    )
    frontier = _select_ready_inspection(
        frontiers,
        project=args.project,
        frontier_id=args.frontier_id,
    )
    target = ExactSubject(
        repository=args.target_repository,
        ref=args.target_ref,
        commit=args.target_head,
    )
    registry_snapshot = _load_project_registry_snapshot()
    token = os.environ.get("PROJECT_RUNNER_GITHUB_TOKEN")
    backend = build_github_read_backend(
        (frontier.subject, target),
        token=token,
    )
    lineage_id = args.lineage_id or (
        "inspect:"
        + frontier_fingerprint(frontier)[:24]
        + ":"
        + args.target_head[:12]
    )
    result = run_durable_github_read_inspection(
        frontier=frontier,
        target_subject=target,
        state_db=args.state_db,
        lineage_id=lineage_id,
        holder=args.holder,
        lease_ttl=args.lease_ttl,
        registry_digest=registry_snapshot.sha256,
        backend=backend,
    )
    payload = {
        "mode": "M6_DURABLE_GITHUB_READ_INSPECTION",
        "status": result.status.value,
        "reason": result.reason,
        "backend_classification": result.backend_classification,
        "lineage_id": result.lineage_id,
        "work_fingerprint": result.work_fingerprint,
        "fencing_token": result.fencing_token,
        "budget_generation": result.budget_generation,
        "work_generation": result.work_generation,
    }
    if not _external_project_registry_selected():
        payload["project"] = frontier.project
        payload["frontier_id"] = frontier.id
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.status is WorkUnitStatus.COMPLETE else 2


def _operator_status(args) -> int:
    if args.detailed:
        _require_public_safe_reporting()
    payload = summarize_recovery_state(
        args.state_db,
        now=time.time(),
        detailed=args.detailed,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("inventory")

    evaluate = subparsers.add_parser("evaluate-change")
    evaluate.add_argument("--before", type=Path, required=True)
    evaluate.add_argument("--after", type=Path, required=True)
    evaluate.add_argument("--dependencies", type=Path, required=True)

    frontier_summary = subparsers.add_parser("frontier-summary")
    frontier_summary.add_argument("--before", type=Path, required=True)
    frontier_summary.add_argument("--after", type=Path, required=True)
    frontier_summary.add_argument("--dependencies", type=Path, required=True)

    frontier_report = subparsers.add_parser("frontier-report")
    frontier_report.add_argument("--before", type=Path, required=True)
    frontier_report.add_argument("--after", type=Path, required=True)
    frontier_report.add_argument("--dependencies", type=Path, required=True)

    dispatch_report = subparsers.add_parser("dispatch-report")
    dispatch_report.add_argument("--before", type=Path, required=True)
    dispatch_report.add_argument("--after", type=Path, required=True)
    dispatch_report.add_argument("--dependencies", type=Path, required=True)

    github_smoke = subparsers.add_parser("github-read-smoke")
    github_smoke.add_argument("--repository", required=True)
    github_smoke.add_argument("--ref", required=True)
    github_smoke.add_argument("--expected-head")

    run_inspection = subparsers.add_parser("run-inspection")
    run_inspection.add_argument("--before", type=Path, required=True)
    run_inspection.add_argument("--after", type=Path, required=True)
    run_inspection.add_argument("--dependencies", type=Path, required=True)
    run_inspection.add_argument("--project", required=True)
    run_inspection.add_argument("--frontier-id")
    run_inspection.add_argument("--target-repository", required=True)
    run_inspection.add_argument("--target-ref", required=True)
    run_inspection.add_argument("--target-head", required=True)
    run_inspection.add_argument(
        "--state-db",
        type=Path,
        default=Path(".project-runner/project-runner.sqlite3"),
    )
    run_inspection.add_argument("--lineage-id")
    run_inspection.add_argument("--holder", default="project-runner-cli")
    run_inspection.add_argument("--lease-ttl", type=float, default=300.0)

    operator_status = subparsers.add_parser("operator-status")
    operator_status.add_argument(
        "--state-db",
        type=Path,
        default=Path(".project-runner/project-runner.sqlite3"),
    )
    operator_status.add_argument("--detailed", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate()
    if args.command == "inventory":
        return _inventory()
    if args.command == "evaluate-change":
        return _evaluate_change(args.before, args.after, args.dependencies)
    if args.command == "frontier-summary":
        return _frontier_summary(args.before, args.after, args.dependencies)
    if args.command == "frontier-report":
        return _frontier_report(args.before, args.after, args.dependencies)
    if args.command == "dispatch-report":
        return _dispatch_report(args.before, args.after, args.dependencies)
    if args.command == "run-inspection":
        return _run_inspection(args)
    if args.command == "operator-status":
        return _operator_status(args)
    return _github_read_smoke(args.repository, args.ref, args.expected_head)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
