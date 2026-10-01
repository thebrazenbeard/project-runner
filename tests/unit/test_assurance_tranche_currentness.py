from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"rezon", "driftguard", "ingest", "project-achilles"}


def test_assurance_tranche_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_assurance_tranche_is_currentness_refreshed_but_not_queued():
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
        or item.source_status.startswith(
            "CURRENTNESS_REFRESHED_GREEN_CANDIDATE_HOSTILE_REVIEWED__EXECUTION_HELD"
        )
        or item.source_status.startswith(
            "CURRENTNESS_REFRESHED_EXACT_MAIN_QUALIFIED__EXECUTION_HELD"
        )
        for item in items.values()
    )


def test_assurance_tranche_does_not_expand_source_effect_ceiling():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = [
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    ]
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items)
