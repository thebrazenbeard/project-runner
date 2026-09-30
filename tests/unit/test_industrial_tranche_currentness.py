from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"abil", "axle"}


def test_industrial_tranche_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_industrial_tranche_is_refreshed_but_held():
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


def test_industrial_review_gates_separate_source_from_effect():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["abil"].review_gate == "DRAFT_RECONCILIATION_AND_ROUTE_ADMISSION"
    assert items["axle"].review_gate == "HARDWARE_EFFECT_QUALIFICATION"
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
