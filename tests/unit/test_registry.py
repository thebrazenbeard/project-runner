from pathlib import Path
import pytest
from runner.registry import load_workers, load_projects


def test_duplicate_worker_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "workers.yaml"
    path.write_text("""
workers:
  - id: same
    name: One
    worker_type: HUMAN
    lifecycle: REGISTERED
    locators: {handle: one}
    roles: []
    routes: {}
  - id: same
    name: Two
    worker_type: HUMAN
    lifecycle: REGISTERED
    locators: {handle: two}
    roles: []
    routes: {}
""", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate worker id: same"):
        load_workers(path)


def test_duplicate_project_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "projects.yaml"
    path.write_text("""
projects:
  - id: same
    name: One
    visibility: public
    repositories: [owner/one]
    capabilities: [read]
  - id: same
    name: Two
    visibility: public
    repositories: [owner/two]
    capabilities: [read]
""", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate project id: same"):
        load_projects(path)
