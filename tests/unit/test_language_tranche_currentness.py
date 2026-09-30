from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"sql-connectome", "unvtrslr"}


def test_language_tranche_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_language_tranche_is_refreshed_but_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert set(items) == TRANCHE
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_EXACT_SOURCE__EXECUTION_HELD")
        for item in items.values()
    )


def test_language_review_gates_preserve_qualification_and_effect_boundaries():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["sql-connectome"].review_gate == "EFFECT_AUTHORITY_SEPARATION"
    assert items["unvtrslr"].review_gate == "EXACT_MAIN_QUALIFICATION"
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
