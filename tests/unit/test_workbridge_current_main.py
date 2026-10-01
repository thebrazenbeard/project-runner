from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]


def test_standalone_workbridge_is_registered_but_not_schedulable():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    project = projects["workbridge"]
    assert project.scheduling_state.value == "HELD"
    assert set(project.capabilities) == {"read", "analyze", "propose"}
    assert project.execution_targets == ()


def test_standalone_workbridge_closes_source_gate_but_holds_effects():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "workbridge"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "INSTALL_RUNTIME_EFFECT_SEPARATION"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_EXACT_MAIN_SOURCE_BUILD_PACKAGE_QUALIFIED__EXECUTION_HELD"
    )
