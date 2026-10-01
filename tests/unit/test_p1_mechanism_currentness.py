from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"roots", "world-zero", "meso-crct"}


def test_p1_mechanism_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_p1_mechanism_tranche_is_refreshed_but_held():
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


def test_p1_mechanism_review_gates_preserve_authority_boundaries():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["roots"].review_gate == "TRUTH_AUTHORITY_SEPARATION"
    assert items["world-zero"].review_gate == "SCIENTIFIC_INTERPRETATION_SEPARATION"
    assert items["meso-crct"].review_gate == "WELFARE_RUNTIME_EFFECT_QUALIFICATION"
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
