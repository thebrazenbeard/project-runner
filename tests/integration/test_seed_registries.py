from pathlib import Path
from runner.registry import load_projects, load_workers

ROOT = Path(__file__).resolve().parents[2]


def test_seed_registry_contains_public_portfolio_without_private_expansion():
    projects = load_projects(ROOT / "registry/projects.yaml")
    workers = load_workers(ROOT / "registry/workers.yaml")

    assert {p.id for p in projects} == {
        "project-runner",
        "chat-communication-bus",
        "vera",
        "vera-control-plane",
        "hc-brain",
        "roots",
        "testament",
        "transcendence",
        "rezon",
        "world-zero",
        "on-theo",
        "wip",
        "mosaic",
    }

    private_projects = {p.id for p in projects if p.visibility == "private"}
    assert private_projects == {
        "chat-communication-bus",
        "vera",
        "vera-control-plane",
    }

    assert len(workers) == 12
    assert all(w.lifecycle.value == "REGISTERED" for w in workers)
