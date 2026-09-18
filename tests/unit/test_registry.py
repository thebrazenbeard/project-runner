import hashlib
from pathlib import Path
import pytest
from runner.registry import load_project_snapshot, load_workers, load_projects


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


def test_project_portfolio_axes_are_parsed(tmp_path: Path):
    path = tmp_path / "projects.yaml"
    path.write_text("""
projects:
  - id: example
    name: Example
    visibility: private
    repositories: [owner/example]
    capabilities: [read, analyze, propose]
    assignment_scope: BT2_ASSIGNMENT
    review_scope: STANDING
    family_id: example-family
    scope_note: explicit test membership
""", encoding="utf-8")
    project = load_projects(path)[0]
    assert project.assignment_scope.value == "BT2_ASSIGNMENT"
    assert project.review_scope.value == "STANDING"
    assert project.family_id == "example-family"
    assert project.scope_note == "explicit test membership"


def test_project_registry_snapshot_binds_exact_bytes(tmp_path: Path):
    path = tmp_path / "projects.yaml"
    first = b"""projects:
  - id: example
    name: Example
    visibility: private
    repositories: [owner/example]
    capabilities: [read]
    assignment_scope: EXTERNAL_BOUNDED
    review_scope: STANDING
    family_id: example-family
    scheduling_state: SCHEDULABLE
"""
    path.write_bytes(first)

    snapshot = load_project_snapshot(path, require_scope_metadata=True)

    assert snapshot.sha256 == hashlib.sha256(first).hexdigest()
    assert snapshot.byte_length == len(first)
    assert tuple(project.id for project in snapshot.projects) == ("example",)

    second = first.replace(b"name: Example", b"name: Example Changed")
    path.write_bytes(second)
    changed = load_project_snapshot(path, require_scope_metadata=True)

    assert changed.sha256 == hashlib.sha256(second).hexdigest()
    assert changed.sha256 != snapshot.sha256
    assert changed.projects[0].name == "Example Changed"
