from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]


def test_achilles_is_exact_main_qualified_but_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "project-achilles"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "CONSUMER_EVIDENCE"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_EXACT_MAIN_QUALIFIED__EXECUTION_HELD"
    )


def test_achilles_registry_does_not_admit_write_or_effect_authority():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    project = projects["project-achilles"]
    assert project.scheduling_state.value == "HELD"
    assert set(project.capabilities) == {"read", "analyze", "propose"}
    assert project.execution_targets == ()
