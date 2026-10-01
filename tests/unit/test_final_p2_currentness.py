from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"god-brain", "transcendence", "vera-r9a0", "vera-habitat", "vera-synology"}


def test_final_p2_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_final_p2_tranche_is_refreshed_but_held():
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


def test_final_p2_review_gates_preserve_lineage_and_effect_boundaries():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["god-brain"].review_gate == "GREEN_CANDIDATE_FALSIFICATION_REVIEW"
    assert items["transcendence"].review_gate == "CURRENT_MAIN_RESTACK_AND_QUALIFICATION"
    assert items["vera-r9a0"].review_gate == "FAILED_CANDIDATE_REMEDIATION"
    assert items["vera-habitat"].review_gate == "CONCRETE_CONSUMER_EVIDENCE"
    assert items["vera-synology"].review_gate == "CANDIDATE_RUNTIME_EFFECT_SEPARATION"
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())


def test_public_repository_currentness_closure_has_no_inherited_markers():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    repository_items = [item for item in wave.items if item.subject_kind == "repository"]
    assert len(repository_items) == 57
    assert not any(
        item.source_status.startswith("INHERITED_SEMANTIC_STATUS_REQUIRES_EXACT_SOURCE_REFRESH")
        for item in repository_items
    )
