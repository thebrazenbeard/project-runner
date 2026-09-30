from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]


def test_unbound_sol_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    project = projects["unbound-sol"]
    assert project.scheduling_state.value == "HELD"
    assert set(project.capabilities) == {"read", "analyze", "propose"}
    assert project.execution_targets == ()


def test_unbound_sol_candidate_is_currentness_bound_but_not_admitted():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "unbound-sol"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.action == "EXECUTE_FRONTIER"
    assert item.review_gate == "CANDIDATE_DAG_RECONCILIATION_AND_ROUTE_ADMISSION"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_EXACT_SOURCE__EXECUTION_HELD"
    )
