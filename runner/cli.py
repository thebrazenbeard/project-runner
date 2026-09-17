from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Sequence

from .currentness import observation_locus, subject_changed
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("inventory")
    evaluate = subparsers.add_parser("evaluate-change")
    evaluate.add_argument("--before", type=Path, required=True)
    evaluate.add_argument("--after", type=Path, required=True)
    evaluate.add_argument("--dependencies", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate()
    if args.command == "inventory":
        return _inventory()
    return _evaluate_change(args.before, args.after, args.dependencies)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
