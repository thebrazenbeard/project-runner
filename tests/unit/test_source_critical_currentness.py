from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
REPOS = {"on-theo", "testament"}
WORKSTREAMS = {"yeshua-real-testament", "nature-of-existence"}


def test_source_critical_repository_routes_are_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in REPOS:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_source_critical_repositories_are_refreshed_but_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in REPOS
    }
    assert set(items) == REPOS
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_EXACT_SOURCE__EXECUTION_HELD")
        for item in items.values()
    )
    assert items["on-theo"].review_gate == "REPAIR_CANDIDATE_AND_CLAIM_BOUNDARY"
    assert items["testament"].review_gate == "EXACT_MAIN_QUALIFICATION_AND_DOWNSTREAM_BOUNDARY"


def test_public_research_workstreams_are_refreshed_but_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "workstream" and item.subject_id in WORKSTREAMS
    }
    assert set(items) == WORKSTREAMS
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_DURABLE_SURFACES__EXECUTION_HELD")
        for item in items.values()
    )
    assert items["yeshua-real-testament"].review_gate == "UPSTREAM_SOURCE_AND_DOWNSTREAM_QUALIFICATION"
    assert items["nature-of-existence"].review_gate == "SOURCE_HYPOTHESIS_BOUNDARY"
