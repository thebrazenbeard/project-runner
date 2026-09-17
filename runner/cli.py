from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Sequence

from .collisions import partition_collision_groups
from .currentness import observation_locus, subject_changed
from .dedup import deduplicate_frontiers, frontier_fingerprint
from .frontier import derive_frontiers
from .prioritize import rank_frontiers
from .propagate import derive_invalidations
from .registry import load_dependencies, load_observations, load_projects, load_workers


ROOT = Path(__file__).resolve().parents[1]


def _load_all():
    projects = load_projects(ROOT / "registry" / "projects.yaml")
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


def _frontier_report(before: Path, after: Path, dependencies: Path) -> int:
    previous = load_observations(before)
    current = load_observations(after)
    edges = load_dependencies(dependencies)
    projects = load_projects(ROOT / "registry" / "projects.yaml")
    capability_lookup = {project.id: set(project.capabilities) for project in projects}

    invalidations = derive_invalidations(previous, current, edges)
    derived = derive_frontiers(invalidations, capability_lookup=capability_lookup)
    frontiers = deduplicate_frontiers(derived)
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("inventory")

    evaluate = subparsers.add_parser("evaluate-change")
    evaluate.add_argument("--before", type=Path, required=True)
    evaluate.add_argument("--after", type=Path, required=True)
    evaluate.add_argument("--dependencies", type=Path, required=True)

    frontier_report = subparsers.add_parser("frontier-report")
    frontier_report.add_argument("--before", type=Path, required=True)
    frontier_report.add_argument("--after", type=Path, required=True)
    frontier_report.add_argument("--dependencies", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate()
    if args.command == "inventory":
        return _inventory()
    if args.command == "evaluate-change":
        return _evaluate_change(args.before, args.after, args.dependencies)
    return _frontier_report(args.before, args.after, args.dependencies)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
