from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Sequence

from .registry import load_projects, load_workers


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-runner")
    parser.add_argument("command", choices=("validate", "inventory"))
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate()
    return _inventory()


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
