from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]


def test_commander_candidate_is_green_but_main_unqualified():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "workbridgecommander"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_MAIN_REQUALIFICATION"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_GREEN_QUALIFICATION_CANDIDATE__MAIN_UNQUALIFIED__EXECUTION_HELD"
    )


def test_commander_registry_does_not_admit_runtime_effect_authority():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    project = projects["workbridgecommander"]
    assert project.scheduling_state.value == "HELD"
    assert set(project.capabilities) == {"read", "analyze", "propose"}
    assert project.execution_targets == ()
