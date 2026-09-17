from pathlib import Path
from runner.registry import load_projects, load_workers

ROOT = Path(__file__).resolve().parents[2]


def test_seed_registry_contains_expected_projects_and_workers():
    projects = load_projects(ROOT / "registry/projects.yaml")
    workers = load_workers(ROOT / "registry/workers.yaml")
    assert {p.id for p in projects} == {
        "project-runner", "chat-communication-bus", "vera",
        "vera-control-plane", "hc-brain"
    }
    assert len(workers) == 12
    assert all(w.lifecycle.value == "REGISTERED" for w in workers)
