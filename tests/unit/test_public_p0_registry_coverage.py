from pathlib import Path

from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry" / "projects.yaml"

EXPECTED_HELD_P0 = {
    "bt2": "thebrazenbeard/bt2",
    "project-lantern": "thebrazenbeard/project-lantern",
    "vera-mesh": "thebrazenbeard/vera-mesh",
    "vera-model-training": "thebrazenbeard/vera_model_training",
    "vera-mono": "thebrazenbeard/vera-mono",
    "workbridgemcp": "thebrazenbeard/WorkBridgeMCP",
}


def test_missing_public_p0_subjects_are_registered_fail_closed():
    projects = {project.id: project for project in load_projects(REGISTRY)}
    for project_id, repository in EXPECTED_HELD_P0.items():
        project = projects[project_id]
        assert project.repositories == (repository,)
        assert project.visibility == "public"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.assignment_scope.value == "EXTERNAL_BOUNDED"
        assert project.review_scope.value == "STANDING"
        assert project.scheduling_state.value == "HELD"
        assert project.execution_targets == ()


def test_p0_registry_coverage_does_not_manufacture_execution_authority():
    projects = {project.id: project for project in load_projects(REGISTRY)}
    forbidden = {"create_branch", "write_branch", "open_pr", "merge"}
    for project_id in EXPECTED_HELD_P0:
        project = projects[project_id]
        assert forbidden.isdisjoint(project.capabilities)
        assert project.scheduling_state.schedulable is False
