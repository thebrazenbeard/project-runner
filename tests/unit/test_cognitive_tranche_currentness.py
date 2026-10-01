from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"fuckup", "hc-brain", "lgcm", "noema"}


def test_cognitive_tranche_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_cognitive_tranche_is_refreshed_but_held():
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


def test_lgcm_alone_remains_blocked_on_exact_main_qualification():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["lgcm"].review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_MAIN_REQUALIFICATION"
    for project_id in {"fuckup", "hc-brain", "noema"}:
        assert items[project_id].review_gate == "EXECUTION_ROUTE_ADMISSION"
